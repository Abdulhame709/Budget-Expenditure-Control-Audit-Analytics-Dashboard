"""PHASE 8 — Import Pipeline views.

Upload → Extract → Preview/Mapping → Validation → Confirmation → Import → Log.
Permissions reuse the existing catalog codes (`imports.view` / `imports.run`)
— the 30-code catalog does NOT change.
"""
from __future__ import annotations

import hashlib

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.permissions import has_perm, require_permission
from apps.governance.services import log_action
from apps.imports import services as svc
from apps.imports.forms import ImportUploadForm, MappingForm
from apps.imports.models import ImportJob

DETAILED_SHEET_PREVIEW_LIMIT = 25


def _fail_extract(job: ImportJob, exc: ValidationError, request) -> None:
    job.status = ImportJob.STATUS_FAILED
    job.log("extract_failed", error=exc.messages[0][:300])
    job.save(update_fields=["status", "job_log", "updated_at"])
    messages.error(request, "فشل الاستخراج: " + exc.messages[0])


def _visible_jobs(user):
    jobs = ImportJob.objects.select_related("created_by")
    if has_perm(user, "users.manage"):
        return jobs
    return jobs.filter(created_by=user)


def _sha256_upload(upload) -> str:
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


# ---------------------------------------------------------------- list
@require_permission("imports.view")
def import_list(request):
    jobs = _visible_jobs(request.user)[:200]
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
            source_sha256 = _sha256_upload(upload)
            if ImportJob.objects.filter(source_sha256=source_sha256).exists():
                form.add_error("source_file", "سبق رفع ملف مطابق إلى النظام؛ لن تُنشأ عملية مكررة.")
                return render(request, "imports/new.html", {"form": form})
            job = ImportJob(
                target=form.cleaned_data["target"],
                source_file=upload,
                original_filename=upload.name,
                source_sha256=source_sha256,
                file_format=fmt,
                created_by=request.user,
            )
            try:
                with transaction.atomic():
                    job.save()
            except IntegrityError:
                if job.source_file.name:
                    job.source_file.storage.delete(job.source_file.name)
                form.add_error("source_file", "سبق رفع ملف مطابق إلى النظام؛ لن تُنشأ عملية مكررة.")
                return render(request, "imports/new.html", {"form": form})
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
                if job.target == ImportJob.TARGET_DETAILED_BUDGET:
                    # re-run the extractor over the saved file to build the sheet archive
                    job.source_file.open("rb")
                    try:
                        sheets, _h, _r, _w, grand_total = svc._extract_detailed_budget(job.source_file.file)
                    finally:
                        job.source_file.close()
                    svc.archive_detailed_budget(job, sheets)
                    job.summary = job.summary or {}
                    job.summary["sheets"] = len(sheets)
                    job.summary["grand_total"] = str(grand_total)
                    job.save(update_fields=["summary", "updated_at"])
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
    job = get_object_or_404(_visible_jobs(request.user), pk=pk)
    can_run = has_perm(request.user, "imports.run")
    mapping_form = None
    preview_rows = []
    if (job.status in (ImportJob.STATUS_EXTRACTED,
                       ImportJob.STATUS_VALIDATED) and job.headers
            and job.target != ImportJob.TARGET_DETAILED_BUDGET):
        mapping_form = MappingForm(
            headers=job.headers, target=job.target, prefix="map",
            initial={k: (job.column_map or {}).get(k, "")
                     for k, _ in svc.get_target_fields(job.target)})
        preview_rows = [
            {"index": r["index"],
             "cells": [r["source"].get(h, "") for h in job.headers]}
            for r in job.rows[:10]
        ]
    detailed_sheets = []
    if job.target == ImportJob.TARGET_DETAILED_BUDGET:
        for sheet in job.detailed_sheets.all():
            row_count = len(sheet.rows)
            detailed_sheets.append({
                "pk": sheet.pk,
                "name": sheet.name,
                "display_title": sheet.display_title,
                "order": sheet.order,
                "headers": sheet.headers,
                "rows": sheet.rows[:DETAILED_SHEET_PREVIEW_LIMIT],
                "row_count": row_count,
                "is_truncated": row_count > DETAILED_SHEET_PREVIEW_LIMIT,
                "sheet_total": sheet.sheet_total,
            })
    context = {
        "job": job,
        "counts": job.summary_counts,
        "mapping_form": mapping_form,
        "can_run": can_run,
        "preview_rows": preview_rows,
        "summary": job.summary or {},
        "target_fields": svc.get_target_fields(job.target),
        "header_labels": svc.header_labels(job.headers, job.target)
        if job.headers else {},
        "detailed_sheets": detailed_sheets,
        "detailed_sheet_preview_limit": DETAILED_SHEET_PREVIEW_LIMIT,
    }
    return render(request, "imports/detail.html", context)


# ---------------------------------------------------------------- validate
@require_permission("imports.run")
@require_POST
def import_validate(request, pk):
    job = get_object_or_404(_visible_jobs(request.user), pk=pk)
    if job.status not in (ImportJob.STATUS_EXTRACTED,
                          ImportJob.STATUS_VALIDATED):
        messages.error(request, "لا يمكن التحقق من هذه الحالة.")
        return redirect("imports:detail", job.pk)
    form = MappingForm(headers=job.headers, target=job.target, data=request.POST, prefix="map")
    if not form.is_valid():
        for field, errs in form.errors.items():
            for msg in errs:
                messages.error(request, f"{msg}")
        return redirect("imports:detail", job.pk)
    job.column_map = {
        key: (form.cleaned_data.get(key) or "")
        for key, _ in svc.get_target_fields(job.target)}
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
    job = get_object_or_404(_visible_jobs(request.user), pk=pk)
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
    job = get_object_or_404(_visible_jobs(request.user), pk=pk)
    try:
        svc.cancel_job(job, request.user, request=request)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("imports:detail", job.pk)
    messages.info(request, "أُلغيت العملية — الملف الأصلي محفوظ كدليل.")
    return redirect("imports:detail", job.pk)


# ---------------------------------------------------------------- column template
@require_permission("imports.view")
def import_template(request, target):
    """Downloadable CSV template: Arabic headers (✓ required) + hint row."""
    valid_targets = {value for value, _label in ImportJob.TARGET_CHOICES}
    if target not in valid_targets:
        raise Http404("هدف استيراد غير معروف")
    csv_text = svc.build_template_csv(target)
    response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="template-{target}.csv"'
    return response


# ---------------------------------------------------------------- original file
@require_permission("imports.view")
def import_file(request, pk):
    job = get_object_or_404(_visible_jobs(request.user), pk=pk)
    log_action(
        action="import_file_downloaded", entity_type="import_job",
        entity_id=job.pk, diff={"file": job.original_filename},
        request=request)
    job.source_file.open("rb")
    return FileResponse(job.source_file, as_attachment=True,
                        filename=job.original_filename)
