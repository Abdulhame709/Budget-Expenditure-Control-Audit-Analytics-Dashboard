"""PHASE 8 — Import Pipeline views.

Upload → Extract → Preview/Mapping → Validation → Confirmation → Import → Log.
Permissions reuse the existing catalog codes (`imports.view` / `imports.run`)
— the 30-code catalog does NOT change.
"""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.permissions import has_perm, require_permission
from apps.governance.services import log_action
from apps.imports import services as svc
from apps.imports.forms import ImportUploadForm, MappingForm
from apps.imports.models import ImportJob
from apps.imports.services import TARGET_FIELDS


def _fail_extract(job: ImportJob, exc: ValidationError, request) -> None:
    job.status = ImportJob.STATUS_FAILED
    job.log("extract_failed", error=exc.messages[0][:300])
    job.save(update_fields=["status", "job_log", "updated_at"])
    messages.error(request, "فشل الاستخراج: " + exc.messages[0])


# ---------------------------------------------------------------- list
@require_permission("imports.view")
def import_list(request):
    jobs = ImportJob.objects.select_related("created_by")[:200]
    return render(request, "imports/list.html", {
        "jobs": jobs, "can_run": has_perm(request.user, "imports.run")})


# ---------------------------------------------------------------- upload
@require_permission("imports.run")
@require_http_methods(["GET", "POST"])
def import_new(request):
    form = ImportUploadForm(request.POST or None, files=request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["source_file"]
        try:
            fmt = svc.detect_format(upload.name)
        except ValidationError as exc:
            form.add_error("source_file", exc)
        else:
            job = ImportJob(
                target=form.cleaned_data["target"],
                source_file=upload,
                original_filename=upload.name,
                file_format=fmt,
                created_by=request.user,
            )
            job.save()
            job.log("uploaded", filename=upload.name, fmt=fmt,
                    size_bytes=upload.size)
            job.save(update_fields=["job_log", "updated_at"])
            log_action(
                action="entity_created", entity_type="import_job",
                entity_id=job.pk,
                diff={"file": upload.name, "format": fmt,
                      "target": job.target, "size_bytes": upload.size},
                request=request)
            try:
                svc.extract_job(job)
            except ValidationError as exc:
                job.refresh_from_db()
                _fail_extract(job, exc, request)
                return redirect("imports:detail", job.pk)
            messages.success(
                request,
                f"رُفع الملف واستُخرج منه {len(job.rows)} صف × "
                f"{len(job.headers)} عمود — راجع المعاينة وطابق الأعمدة.")
            return redirect("imports:detail", job.pk)
    return render(request, "imports/new.html", {"form": form})


# ---------------------------------------------------------------- detail
@require_permission("imports.view")
def import_detail(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    can_run = has_perm(request.user, "imports.run")
    mapping_form = None
    preview_rows = []
    if job.status in (ImportJob.STATUS_EXTRACTED,
                      ImportJob.STATUS_VALIDATED) and job.headers:
        mapping_form = MappingForm(
            headers=job.headers, prefix="map",
            initial={k: (job.column_map or {}).get(k, "")
                     for k, _ in TARGET_FIELDS})
        preview_rows = [
            {"index": r["index"],
             "cells": [r["source"].get(h, "") for h in job.headers]}
            for r in job.rows[:10]
        ]
    context = {
        "job": job,
        "counts": job.summary_counts,
        "mapping_form": mapping_form,
        "can_run": can_run,
        "preview_rows": preview_rows,
        "summary": job.summary or {},
        "target_fields": TARGET_FIELDS,
    }
    return render(request, "imports/detail.html", context)


# ---------------------------------------------------------------- validate
@require_permission("imports.run")
@require_POST
def import_validate(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    if job.status not in (ImportJob.STATUS_EXTRACTED,
                          ImportJob.STATUS_VALIDATED):
        messages.error(request, "لا يمكن التحقق من هذه الحالة.")
        return redirect("imports:detail", job.pk)
    form = MappingForm(headers=job.headers, data=request.POST, prefix="map")
    if not form.is_valid():
        for field, errs in form.errors.items():
            for msg in errs:
                messages.error(request, f"{msg}")
        return redirect("imports:detail", job.pk)
    job.column_map = {
        key: (form.cleaned_data.get(key) or "") for key, _ in TARGET_FIELDS}
    job.save(update_fields=["column_map", "updated_at"])
    try:
        summary = svc.validate_job(job, request.user, request=request)
    except ValidationError as exc:
        messages.error(request, "تعذّر التحقق: " + " ".join(exc.messages))
        return redirect("imports:detail", job.pk)
    log_action(
        action="entity_updated", entity_type="import_job", entity_id=job.pk,
        diff={"stage": "validated",
              **{k: summary[k] for k in
                 ("total", "valid", "invalid", "duplicate", "errors",
                  "warnings")}},
        request=request)
    messages.success(
        request,
        f"اكتمل التحقق — {summary['valid']} صف صالح من {summary['total']} "
        f"(غير صالح: {summary['invalid']} · مكرر: {summary['duplicate']}).")
    return redirect("imports:detail", job.pk)


# ---------------------------------------------------------------- confirm
@require_permission("imports.run")
@require_POST
def import_confirm(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    try:
        imported = svc.run_import(job, request.user, request=request)
    except ValidationError as exc:
        messages.error(request, "تعذّر التنفيذ: " + " ".join(exc.messages))
        return redirect("imports:detail", job.pk)
    messages.success(
        request,
        f"تم استيراد {imported} صف بنجاح — سُجّلت العملية في سجل الاستيراد "
        f"ودليل التدقيق. الملف الأصلي محفوظ.")
    return redirect("imports:detail", job.pk)


# ---------------------------------------------------------------- cancel
@require_permission("imports.run")
@require_POST
def import_cancel(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    try:
        svc.cancel_job(job, request.user, request=request)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("imports:detail", job.pk)
    messages.info(request, "أُلغيت العملية — الملف الأصلي محفوظ كدليل.")
    return redirect("imports:detail", job.pk)


# ---------------------------------------------------------------- original file
@require_permission("imports.view")
def import_file(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    log_action(
        action="import_file_downloaded", entity_type="import_job",
        entity_id=job.pk, diff={"file": job.original_filename},
        request=request)
    job.source_file.open("rb")
    return FileResponse(job.source_file, as_attachment=True,
                        filename=job.original_filename)
