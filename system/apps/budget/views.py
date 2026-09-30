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
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import has_perm, require_permission
from apps.governance.models import AuditLog
from apps.reference.services import changes_between, log_action, snapshot

from . import forms, services
from .models import Budget, BudgetLine, BudgetVersion, MONTH_FIELDS


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
def version_detail(request, pk):
    version = get_object_or_404(
        BudgetVersion.objects.select_related("budget__fiscal_year"), pk=pk)
    lines = version.lines.select_related(
        "department", "account", "expense_category")
    totals = services.version_totals(version)
    can_edit = has_perm(request.user, "budget.edit")
    locked = version.is_approved  # approved ⇒ lines locked
    return render(request, "budget/version_detail.html", {
        "version": version, "budget": version.budget, "lines": lines,
        "totals": totals, "can_edit": can_edit, "locked": locked,
        "is_analysis": version.is_analysis_version,
        "summary_url": reverse("budget:version_summary", args=[version.pk]),
        "approve_url": reverse("budget:version_approve", args=[version.pk]),
        "unapprove_url": reverse("budget:version_unapprove", args=[version.pk]),
        "edit_notes_url": reverse("budget:version_edit", args=[version.pk]),
        "line_create_url": reverse("budget:line_create", args=[version.pk]),
        "new_revision_url": reverse(
            "budget:version_new_revision", args=[version.budget_id]),
    })


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
