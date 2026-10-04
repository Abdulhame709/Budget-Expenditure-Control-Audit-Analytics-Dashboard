"""PHASE 5 — Budget Management views.

Flow: Budget (one/FY) → BudgetVersion (draft ⇄ approved; revision = new
version copying lines) → BudgetLine (manual monthly entry).

Enforcement:
- page   : URL_PERMISSIONS (budget.view / budget.edit) via middleware
- action : @require_permission on every mutation
- object : APPROVED versions are locked (line edits need a new revision)
- numbers: every total comes from DB aggregates (services.py)
"""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import has_perm, require_permission
from apps.governance.models import AuditLog
from apps.reference.services import changes_between, log_action, snapshot

from . import forms, services
from .models import (
    MONTH_FIELDS,
    Budget,
    BudgetLine,
    BudgetTemplate,
    BudgetTemplateRow,
    BudgetTemplateSheet,
    BudgetVersion,
)
from .template_import import import_budget_workbook


# ---------------------------------------------------------------- list
def budget_list(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    fy = (request.GET.get("fy") or "").strip()

    qs = Budget.objects.select_related("fiscal_year")
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(fiscal_year__code__icontains=q)
            | Q(fiscal_year__name__icontains=q)
        )
    if status in dict(BudgetVersion.STATUS_CHOICES):
        qs = qs.filter(versions__status=status).distinct()
    if fy.isdigit():
        qs = qs.filter(fiscal_year_id=int(fy))

    paginator = Paginator(qs, 15)
    try:
        page = paginator.get_page(request.GET.get("page"))
    except PageNotAnInteger:
        page = paginator.get_page(1)
    except EmptyPage:
        page = paginator.get_page(paginator.num_pages)

    rows = []
    for b in page:
        latest = b.latest_version
        analysis = b.analysis_version
        rows.append({
            "obj": b,
            "latest": latest,
            "analysis": analysis,
            "url": reverse("budget:budget_detail", args=[b.pk]),
        })

    return render(request, "budget/budget_list.html", {
        "rows": rows, "q": q, "total": paginator.count, "page_obj": page,
        "active_status": status,
        "status_choices": BudgetVersion.STATUS_CHOICES,
        "can_edit": has_perm(request.user, "budget.edit"),
        "create_url": reverse("budget:budget_create"),
    })


# ---------------------------------------------------------------- header CRUD
@require_permission("budget.edit")
def budget_create(request):
    if request.method == "POST":
        form = forms.BudgetForm(request.POST)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.created_by = request.user
            budget.updated_by = request.user
            budget.save()
            version = BudgetVersion.objects.create(
                budget=budget, version=1, status=BudgetVersion.STATUS_DRAFT,
            )
            log_action(action="entity_created", entity_type="budget",
                       entity_id=budget.pk, diff=snapshot(budget), request=request)
            log_action(action="budget_version_created", entity_type="budgetversion",
                       entity_id=version.pk,
                       diff={"budget": str(budget), "version": 1,
                             "reason": "إنشاء الميزانية"},
                       request=request)
            messages.success(request, f"تم إنشاء الميزانية «{budget}» ونسخة المسودة v1.")
            return redirect("budget:budget_detail", pk=budget.pk)
    else:
        form = forms.BudgetForm()
    return render(request, "budget/budget_form.html", {
        "form": form, "is_create": True, "title": "ميزانية جديدة",
        "cancel_url": reverse("budget:budget_list"),
    })


def budget_detail(request, pk):
    budget = get_object_or_404(Budget.objects.select_related("fiscal_year"), pk=pk)
    versions = []
    for v in budget.versions.all():
        versions.append({
            "obj": v,
            "is_analysis": budget.analysis_version is not None
            and budget.analysis_version.pk == v.pk,
            "totals": services.version_totals(v),
        })
    return render(request, "budget/budget_detail.html", {
        "budget": budget, "versions": versions,
        "analysis": budget.analysis_version,
        "can_edit": has_perm(request.user, "budget.edit"),
        "line_form_url_base": None,
        "edit_url": reverse("budget:budget_edit", args=[budget.pk]),
        "delete_url": reverse("budget:budget_delete", args=[budget.pk]),
        "new_revision_url": reverse("budget:version_new_revision", args=[budget.pk])
        if budget.latest_version else "",
    })


@require_permission("budget.edit")
def budget_edit(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    before = snapshot(budget, ["name", "notes"])
    if request.method == "POST":
        form = forms.BudgetEditForm(request.POST, instance=budget)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.updated_by = request.user
            budget.save()
            diff = changes_between(budget, before)
            if diff:
                log_action(action="entity_updated", entity_type="budget",
                           entity_id=budget.pk, diff=diff, request=request)
                messages.success(request, "تم تعديل الميزانية وتسجيل الفروق في سجل التدقيق.")
            else:
                messages.info(request, "لا توجد تغييرات لحفظها.")
            return redirect("budget:budget_detail", pk=budget.pk)
    else:
        form = forms.BudgetEditForm(instance=budget)
    return render(request, "budget/budget_form.html", {
        "form": form, "is_create": False, "title": f"تعديل: {budget}",
        "cancel_url": reverse("budget:budget_detail", args=[budget.pk]),
    })


@require_permission("budget.edit")
def budget_delete(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    if request.method != "POST":
        messages.error(request, "الحذف يتطلب تأكيدًا (POST).")
        return redirect("budget:budget_detail", pk=pk)
    if budget.versions.filter(status=BudgetVersion.STATUS_APPROVED).exists():
        messages.error(
            request,
            "لا يمكن حذف ميزانية تحتوي نسخة معتمدة — الاعتماد يعني أن الأرقام "
            "أصبحت أساس التحليل. (أنشئ نسخة مراجعة بدلًا من ذلك.)",
        )
        return redirect("budget:budget_detail", pk=pk)
    before = snapshot(budget, ["name", "notes", "fiscal_year"])
    label = str(budget)
    budget.delete()
    log_action(action="entity_deleted", entity_type="budget",
               entity_id=pk, diff={"snapshot": before, "label": label},
               request=request)
    messages.success(request, f"تم حذف الميزانية «{label}» وتسجيله في سجل التدقيق.")
    return redirect("budget:budget_list")


# ---------------------------------------------------------------- versions
def _version_detail_context(request, version, *, grid_forms=None):
    lines = list(version.lines.select_related(
        "department", "account", "expense_category"))
    totals = services.version_totals(version)
    can_edit = has_perm(request.user, "budget.edit")
    locked = version.is_approved  # approved ⇒ lines locked
    if grid_forms is None and can_edit and not locked:
        grid_forms = [
            forms.BudgetLineGridForm(instance=line, prefix=f"line-{line.pk}")
            for line in lines
        ]
    form_by_line_id = {
        form.instance.pk: form for form in (grid_forms or [])
    }
    grid_rows = [
        {"line": line, "form": form_by_line_id.get(line.pk)}
        for line in lines
    ]
    return {
        "version": version, "budget": version.budget, "lines": lines,
        "grid_rows": grid_rows,
        "totals": totals, "can_edit": can_edit, "locked": locked,
        "is_analysis": version.is_analysis_version,
        "summary_url": reverse("budget:version_summary", args=[version.pk]),
        "approve_url": reverse("budget:version_approve", args=[version.pk]),
        "unapprove_url": reverse("budget:version_unapprove", args=[version.pk]),
        "edit_notes_url": reverse("budget:version_edit", args=[version.pk]),
        "line_create_url": reverse("budget:line_create", args=[version.pk]),
        "grid_update_url": reverse(
            "budget:version_grid_update", args=[version.pk]),
        "new_revision_url": reverse(
            "budget:version_new_revision", args=[version.budget_id]),
    }


def version_detail(request, pk):
    version = get_object_or_404(
        BudgetVersion.objects.select_related("budget__fiscal_year"), pk=pk)
    return render(
        request,
        "budget/version_detail.html",
        _version_detail_context(request, version),
    )


@require_permission("budget.edit")
@require_POST
def version_grid_update(request, pk):
    version = get_object_or_404(
        BudgetVersion.objects.select_related("budget__fiscal_year"), pk=pk)
    _require_draft(version, "التعديل الشبكي")
    lines = list(version.lines.select_related(
        "department", "account", "expense_category"))
    if not lines:
        messages.info(request, "لا توجد سطور موازنة لتعديلها.")
        return redirect("budget:version_detail", pk=version.pk)

    before_by_line_id = {
        line.pk: snapshot(line, [*MONTH_FIELDS, "annual_amount"])
        for line in lines
    }
    grid_forms = [
        forms.BudgetLineGridForm(
            request.POST, instance=line, prefix=f"line-{line.pk}"
        )
        for line in lines
    ]
    validation_results = [form.is_valid() for form in grid_forms]
    if not all(validation_results):
        messages.error(
            request,
            "لم تُحفظ التغييرات: صحّح القيم المعلّمة داخل جدول الموازنة.",
        )
        return render(
            request,
            "budget/version_detail.html",
            _version_detail_context(request, version, grid_forms=grid_forms),
            status=400,
        )

    changed_count = 0
    with transaction.atomic():
        for form in grid_forms:
            line = form.instance
            before = before_by_line_id[line.pk]
            line = form.save(commit=False)
            line.updated_by = request.user
            line.save()
            diff = changes_between(line, before)
            if diff:
                changed_count += 1
                log_action(
                    action="entity_updated",
                    entity_type="budgetline",
                    entity_id=line.pk,
                    diff=diff,
                    request=request,
                )

    if changed_count:
        messages.success(
            request,
            f"تم حفظ {changed_count} من سطور الموازنة وتسجيل الفروق.",
        )
    else:
        messages.info(request, "لم توجد تغييرات جديدة للحفظ.")
    return redirect("budget:version_detail", pk=version.pk)


@require_permission("budget.edit")
def version_edit(request, pk):
    version = get_object_or_404(BudgetVersion, pk=pk)
    before = snapshot(version, ["notes"])
    if request.method == "POST":
        form = forms.BudgetVersionForm(request.POST, instance=version)
        if form.is_valid():
            version = form.save(commit=False)
            version.updated_by = request.user
            version.save()
            diff = changes_between(version, before)
            if diff:
                log_action(action="entity_updated", entity_type="budgetversion",
                           entity_id=version.pk, diff=diff, request=request)
                messages.success(request, "تم حفظ ملاحظات النسخة.")
            return redirect("budget:version_detail", pk=version.pk)
    else:
        form = forms.BudgetVersionForm(instance=version)
    return render(request, "budget/budget_form.html", {
        "form": form, "is_create": False,
        "title": f"ملاحظات النسخة: {version}",
        "cancel_url": reverse("budget:version_detail", args=[version.pk]),
    })


@require_permission("budget.edit")
def version_approve(request, pk):
    """draft → approved: locks the version and makes it eligible for analysis."""
    version = get_object_or_404(BudgetVersion, pk=pk)
    if request.method != "POST":
        messages.error(request, "الاعتماد يتطلب POST.")
        return redirect("budget:version_detail", pk=pk)
    if version.is_approved:
        messages.info(request, "النسخة معتمدة بالفعل.")
        return redirect("budget:version_detail", pk=pk)
    if not version.lines.exists():
        messages.error(request, "لا يمكن اعتماد نسخة بلا سطور ميزانية.")
        return redirect("budget:version_detail", pk=pk)
    version.status = BudgetVersion.STATUS_APPROVED
    version.approved_by = request.user
    version.approved_at = timezone.now()
    version.updated_by = request.user
    version.save(update_fields=["status", "approved_by", "approved_at",
                                "updated_by", "updated_at"])
    log_action(action="budget_approved", entity_type="budgetversion",
               entity_id=version.pk,
               diff={"version": str(version), "lines": version.lines.count(),
                     "annual_total": str(services.version_totals(version)["annual_total"])},
               request=request)
    messages.success(
        request,
        f"تم اعتماد النسخة {version} وأصبحت هي النسخة المستخدمة في التحليل — "
        "وأُقفلت للتعديل (التعديل عبر نسخة مراجعة جديدة).",
    )
    return redirect("budget:version_detail", pk=version.pk)


@require_permission("budget.edit")
def version_unapprove(request, pk):
    version = get_object_or_404(BudgetVersion, pk=pk)
    if request.method != "POST":
        messages.error(request, "الإجراء يتطلب POST.")
        return redirect("budget:version_detail", pk=pk)
    if not version.is_approved:
        messages.info(request, "النسخة ليست معتمدة.")
        return redirect("budget:version_detail", pk=pk)
    version.status = BudgetVersion.STATUS_DRAFT
    version.approved_by = None
    version.approved_at = None
    version.updated_by = request.user
    version.save(update_fields=["status", "approved_by", "approved_at",
                                "updated_by", "updated_at"])
    log_action(action="budget_unapproved", entity_type="budgetversion",
               entity_id=version.pk, diff={"version": str(version)},
               request=request)
    messages.warning(request, f"تم إلغاء اعتماد النسخة {version} وأصبحت مسودة قابلة للتعديل.")
    return redirect("budget:version_detail", pk=version.pk)


@require_permission("budget.edit")
def version_new_revision(request, budget_pk):
    """Revised budget: version N+1 (draft) copying all lines of the
    latest version — the approved one stays intact for analysis."""
    budget = get_object_or_404(Budget, pk=budget_pk)
    if request.method != "POST":
        messages.error(request, "الإجراء يتطلب POST.")
        return redirect("budget:budget_detail", pk=budget.pk)
    source = budget.latest_version
    if source is None:
        messages.error(request, "لا توجد نسخة لنسخها.")
        return redirect("budget:budget_detail", pk=budget.pk)
    new_version = BudgetVersion.objects.create(
        budget=budget, version=source.version + 1,
        status=BudgetVersion.STATUS_DRAFT, created_by=request.user,
        updated_by=request.user,
        notes=f"مراجعة للنسخة {source.version}" + (
            " (المعتمدة)" if source.is_approved else ""),
    )
    copied = 0
    for line in source.lines.all():
        BudgetLine.objects.create(
            version=new_version, department_id=line.department_id,
            account_id=line.account_id,
            expense_category_id=line.expense_category_id,
            **{f: getattr(line, f) for f in MONTH_FIELDS},
            annual_amount=line.annual_amount, notes=line.notes,
            created_by=request.user, updated_by=request.user,
        )
        copied += 1
    log_action(action="budget_version_created", entity_type="budgetversion",
               entity_id=new_version.pk,
               diff={"budget": str(budget), "version": new_version.version,
                     "copied_from": source.version, "lines_copied": copied,
                     "reason": "نسخة مراجعة (Revised Budget)"},
               request=request)
    messages.success(
        request,
        f"أُنشئت نسخة المراجعة v{new_version.version} بنسخ {copied} سطرًا من "
        f"v{source.version} — عدّل ما يلزم ثم اعتمد النسخة الجديدة.",
    )
    return redirect("budget:version_detail", pk=new_version.pk)


# ---------------------------------------------------------------- lines
def _require_draft(version, action_label: str):
    if version.is_approved:
        raise PermissionDenied(
            f"النسخة {version} معتمدة ومُقفلة — {action_label} متاح فقط على "
            "المسودات. أنشئ نسخة مراجعة (Revised Budget) ثم عدّل فيها."
        )


@require_permission("budget.edit")
def line_create(request, version_pk):
    version = get_object_or_404(BudgetVersion, pk=version_pk)
    _require_draft(version, "إضافة سطر")
    if request.method == "POST":
        form = forms.BudgetLineForm(request.POST)
        if form.is_valid():
            line = form.save(commit=False)
            line.version = version
            line.created_by = request.user
            line.updated_by = request.user
            line.save()
            log_action(action="entity_created", entity_type="budgetline",
                       entity_id=line.pk, diff=snapshot(line), request=request)
            messages.success(
                request,
                f"أُضيف السطر {line} (السنوية {line.annual_amount}) وسُجِّل في سجل التدقيق.",
            )
            return redirect("budget:version_detail", pk=version.pk)
    else:
        form = forms.BudgetLineForm()
    return render(request, "budget/line_form.html", {
        "form": form, "version": version, "is_create": True,
        "cancel_url": reverse("budget:version_detail", args=[version.pk]),
    })


@require_permission("budget.edit")
def line_edit(request, pk):
    line = get_object_or_404(
        BudgetLine.objects.select_related("version__budget"), pk=pk)
    _require_draft(line.version, "تعديل سطر")
    before = snapshot(line)
    if request.method == "POST":
        form = forms.BudgetLineForm(request.POST, instance=line)
        if form.is_valid():
            line = form.save(commit=False)
            line.updated_by = request.user
            line.save()
            diff = changes_between(line, before)
            if diff:
                log_action(action="entity_updated", entity_type="budgetline",
                           entity_id=line.pk, diff=diff, request=request)
                messages.success(
                    request,
                    f"عُدّل السطر {line} (السنوية الجديدة {line.annual_amount}) "
                    "والفروق مُسجَّلة.",
                )
            return redirect("budget:version_detail", pk=line.version_id)
    else:
        form = forms.BudgetLineForm(instance=line)
    return render(request, "budget/line_form.html", {
        "form": form, "version": line.version, "is_create": False, "line": line,
        "cancel_url": reverse("budget:version_detail", args=[line.version_id]),
    })


@require_permission("budget.edit")
def line_delete(request, pk):
    line = get_object_or_404(
        BudgetLine.objects.select_related("version__budget"), pk=pk)
    _require_draft(line.version, "حذف سطر")
    if request.method != "POST":
        messages.error(request, "الحذف يتطلب تأكيدًا (POST).")
        return redirect("budget:version_detail", pk=line.version_id)
    before = snapshot(line)
    label, version_id = str(line), line.version_id
    line.delete()
    log_action(action="entity_deleted", entity_type="budgetline", entity_id=pk,
               diff={"snapshot": before, "label": label}, request=request)
    messages.success(request, f"حُذف السطر «{label}» وسُجِّل في سجل التدقيق.")
    return redirect("budget:version_detail", pk=version_id)


# ---------------------------------------------------------------- summary
def version_summary(request, pk):
    """Budget-vs-Actual foundation: DB-computed totals for ONE version,
    with an explicit banner stating whether this version is THE analysis
    version. (Actuals/Variance arrive in a later phase.)"""
    version = get_object_or_404(
        BudgetVersion.objects.select_related("budget__fiscal_year"), pk=pk)
    totals = services.version_totals(version)
    context = {
        "version": version, "budget": version.budget, "totals": totals,
        "by_department": services.totals_by(version, "department"),
        "by_account": services.totals_by(version, "account"),
        "by_category": services.totals_by(version, "expense_category"),
        "is_analysis": version.is_analysis_version,
        "back_url": reverse("budget:version_detail", args=[version.pk]),
    }
    return render(request, "budget/summary.html", context)


# ---------------------------------------------------------------- configurable budget templates
def template_list(request):
    q = (request.GET.get("q") or "").strip()
    queryset = BudgetTemplate.objects.select_related("currency").annotate(
        sheet_count=Count("sheets", distinct=True),
        mapped_rows=Count("sheets__rows", filter=Q(sheets__rows__account__isnull=False)),
    )
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) | Q(source_filename__icontains=q)
        )
    return render(request, "budget/template_list.html", {
        "templates": queryset,
        "q": q,
        "can_edit": has_perm(request.user, "budget.edit"),
    })


@require_permission("budget.edit")
def template_import(request):
    if request.method == "POST":
        form = forms.BudgetTemplateImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                template = import_budget_workbook(
                    form.cleaned_data["workbook"],
                    name=form.cleaned_data["name"],
                    description=form.cleaned_data["description"],
                    user=request.user,
                )
            except Exception as exc:
                form.add_error(
                    "workbook",
                    f"تعذر قراءة المصنف. تأكد من سلامة ملف Excel: {exc}",
                )
            else:
                log_action(
                    action="budget_template_imported",
                    entity_type="budgettemplate",
                    entity_id=template.pk,
                    diff={
                        "name": template.name,
                        "source_filename": template.source_filename,
                        "sheet_count": template.sheets.count(),
                    },
                    request=request,
                )
                messages.success(
                    request,
                    f"تم استيراد النموذج «{template.name}» مع {template.sheets.count()} ورقة.",
                )
                return redirect("budget:template_detail", pk=template.pk)
    else:
        form = forms.BudgetTemplateImportForm()
    return render(request, "budget/template_import.html", {"form": form})


def template_detail(request, pk):
    template = get_object_or_404(
        BudgetTemplate.objects.select_related("currency"), pk=pk,
    )
    sheets = template.sheets.annotate(
        populated_rows=Count("rows", distinct=True),
        mapped_rows=Count("rows", filter=Q(rows__account__isnull=False)),
    )
    return render(request, "budget/template_detail.html", {
        "template": template,
        "sheets": sheets,
        "can_edit": has_perm(request.user, "budget.edit"),
    })


@require_permission("budget.edit")
def template_edit(request, pk):
    template = get_object_or_404(BudgetTemplate, pk=pk)
    before = snapshot(template, ["name", "description", "currency", "is_active"])
    if request.method == "POST":
        form = forms.BudgetTemplateForm(request.POST, instance=template)
        if form.is_valid():
            template = form.save(commit=False)
            template.updated_by = request.user
            template.save()
            diff = changes_between(template, before)
            if diff:
                log_action(
                    action="entity_updated", entity_type="budgettemplate",
                    entity_id=template.pk, diff=diff, request=request,
                )
            messages.success(request, "تم تحديث إعدادات نموذج الموازنة.")
            return redirect("budget:template_detail", pk=template.pk)
    else:
        form = forms.BudgetTemplateForm(instance=template)
    return render(request, "budget/template_edit.html", {
        "form": form,
        "template": template,
    })


@require_permission("budget.edit")
@require_POST
def template_delete(request, pk):
    template = get_object_or_404(BudgetTemplate, pk=pk)
    source_filename = template.source_filename
    label = template.name
    template.delete()
    log_action(
        action="entity_deleted", entity_type="budgettemplate", entity_id=pk,
        diff={"name": label, "source_filename": source_filename}, request=request,
    )
    messages.success(request, f"تم حذف نموذج الموازنة «{label}».")
    return redirect("budget:template_list")


def template_sheet(request, pk):
    sheet = get_object_or_404(
        BudgetTemplateSheet.objects.select_related("template"), pk=pk,
    )
    columns = list(sheet.columns.all())
    row_queryset = sheet.rows.select_related("account").prefetch_related(
        "cells__column"
    )
    paginator = Paginator(row_queryset, 100)
    page = paginator.get_page(request.GET.get("page"))
    can_edit = has_perm(request.user, "budget.edit")

    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied("لا تملك صلاحية تعديل نماذج الموازنة.")
        sheet_form = forms.BudgetTemplateSheetForm(
            request.POST, instance=sheet, prefix="sheet",
        )
        row_forms = [
            forms.BudgetTemplateRowMappingForm(
                request.POST, instance=row, prefix=f"row-{row.pk}"
            )
            for row in page.object_list
        ]
        if sheet_form.is_valid() and all(form.is_valid() for form in row_forms):
            with transaction.atomic():
                changed_rows = 0
                old_purpose = sheet.purpose
                updated_sheet = sheet_form.save(commit=False)
                updated_sheet.updated_by = request.user
                updated_sheet.save()
                for row_form in row_forms:
                    if row_form.has_changed():
                        row_form.save()
                        changed_rows += 1
            log_action(
                action="budget_template_mapping_updated",
                entity_type="budgettemplatesheet",
                entity_id=sheet.pk,
                diff={
                    "purpose": {"before": old_purpose, "after": sheet.purpose},
                    "changed_rows": changed_rows,
                    "page": page.number,
                },
                request=request,
            )
            messages.success(
                request,
                f"تم حفظ تصنيف الورقة وربط {changed_rows} صفًا.",
            )
            return redirect(f"{reverse('budget:template_sheet', args=[sheet.pk])}?page={page.number}")
    else:
        sheet_form = forms.BudgetTemplateSheetForm(instance=sheet, prefix="sheet")
        row_forms = [
            forms.BudgetTemplateRowMappingForm(instance=row, prefix=f"row-{row.pk}")
            for row in page.object_list
        ]

    rows = []
    for row, row_form in zip(page.object_list, row_forms):
        cells_by_column = {cell.column_id: cell for cell in row.cells.all()}
        rows.append({
            "row": row,
            "form": row_form,
            "cells": [cells_by_column.get(column.pk) for column in columns],
        })
    return render(request, "budget/template_sheet.html", {
        "sheet": sheet,
        "template": sheet.template,
        "columns": columns,
        "rows": rows,
        "page_obj": page,
        "sheet_form": sheet_form,
        "can_edit": can_edit,
    })
