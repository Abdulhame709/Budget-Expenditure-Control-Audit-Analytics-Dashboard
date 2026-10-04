"""PHASE 6 — Actual Expenses views.

List/Search/Filters/Details/Create/Edit/Attachment/Export — every
mutation audited (entity_created/entity_updated), every file view
audited (expense_attachment_viewed), every export audited
(expenses_exported), and posting always goes through
reference.services.require_period_postable (closed period ⇒
periods.post_closed + closed_period_override audit entry).

No dashboard in this phase.
"""
from __future__ import annotations

import csv
import mimetypes

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import has_perm, require_permission
from apps.expenses import services
from apps.governance.models import AuditLog
from config.csv_safety import safe_spreadsheet_value
from apps.reference.services import (
    changes_between,
    log_action,
    require_period_postable,
    snapshot,
)

from . import forms
from .models import Expense

APPROVAL_FIELDS = [
    "expense_number", "expense_date", "period", "department", "account",
    "expense_category", "supplier", "description", "amount", "currency",
    "payment_method", "payment_reference", "invoice_reference",
    "approval_reference", "approved_by", "approved_at",
]


# ---------------------------------------------------------------- shared
def _filtered(request):
    """Search + filters shared by list & export (one source of truth)."""
    qs = Expense.objects.select_related(
        "period__fiscal_year", "department", "account",
        "expense_category", "supplier", "created_by")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(expense_number__icontains=q)
            | Q(description__icontains=q)
            | Q(payment_reference__icontains=q)
            | Q(invoice_reference__icontains=q)
            | Q(supplier__name__icontains=q)
            | Q(supplier__code__icontains=q)
        )
    for param, lookup in (
        ("period", "period_id"), ("department", "department_id"),
        ("account", "account_id"), ("category", "expense_category_id"),
        ("supplier", "supplier_id"), ("currency", "currency"),
    ):
        raw = (request.GET.get(param) or "").strip()
        if raw.isdigit():
            qs = qs.filter(**{lookup: int(raw)})
        elif param == "currency" and raw in dict(Expense.CURRENCY_CHOICES):
            qs = qs.filter(currency=raw)
    approval = (request.GET.get("approval") or "").strip()
    if approval == "approved":
        qs = qs.filter(approval_reference__isnull=False).exclude(
            approval_reference="")
    elif approval == "unapproved":
        qs = qs.filter(Q(approval_reference__isnull=True)
                       | Q(approval_reference=""))
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)
    return qs, q


def _filter_context(request) -> dict:
    from apps.reference.models import Department, ExpenseCategory, Account, Supplier
    from apps.reference.models import MonthlyPeriod
    return {
        "filter_options": {
            "periods": MonthlyPeriod.objects.select_related("fiscal_year"),
            "departments": Department.objects.filter(is_active=True),
            "accounts": Account.objects.filter(account_type="expense"),
            "categories": ExpenseCategory.objects.filter(is_active=True),
            "suppliers": Supplier.objects.filter(is_active=True),
            "currencies": Expense.CURRENCY_CHOICES,
            "approvals": [("", "الكل"), ("unapproved", "بلا اعتماد"),
                          ("approved", "معتمد")],
        },
        "sel": {k: (request.GET.get(k) or "")
                for k in ("period", "department", "account", "category",
                          "supplier", "currency", "approval",
                          "date_from", "date_to")},
    }


# ---------------------------------------------------------------- list
def expense_list(request):
    qs, q = _filtered(request)
    filtered_total = qs.aggregate(total=Sum("amount"))["total"]
    paginator = Paginator(qs, 15)
    try:
        page = paginator.get_page(request.GET.get("page"))
    except PageNotAnInteger:
        page = paginator.get_page(1)
    except EmptyPage:
        page = paginator.get_page(paginator.num_pages)
    return render(request, "expenses/list.html", {
        "rows": page, "q": q, "total": paginator.count,
        "filtered_total": filtered_total, "page_obj": page,
        "can_edit": has_perm(request.user, "expenses.edit"),
        "create_url": reverse("expenses:create"),
        "export_url": reverse("expenses:export") + (
            "?" + request.GET.urlencode() if request.GET.urlencode() else ""),
        **_filter_context(request),
    })


# ---------------------------------------------------------------- create / edit
def _apply_approval(expense, ref, original_ref, user):
    """Approval block: a NEW reference stamps approver/time; clearing it
    resets them. (`original_ref` = DB value BEFORE form.save mutated it.)"""
    ref = (ref or "").strip()
    if ref and (ref != original_ref or expense.approved_by_id is None):
        expense.approved_by = user
        expense.approved_at = timezone.now()
    elif not ref and original_ref:
        expense.approved_by = None
        expense.approved_at = None
    expense.approval_reference = ref


@require_permission("expenses.edit")
def expense_create(request):
    if request.method == "POST":
        form = forms.ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            if not expense.expense_number:
                expense.expense_number = services.next_expense_number(
                    expense.expense_date)
            expense.created_by = request.user
            expense.updated_by = request.user
            _apply_approval(expense, form.cleaned_data.get("approval_reference"),
                            "", request.user)
            # CLOSED-PERIOD RULE (PHASE 4) — first real enforcement point:
            # PermissionDenied ⇒ 403; allowed override ⇒ audit row.
            require_period_postable(
                request.user, expense.period,
                purpose=f"مصروف {expense.expense_number}", request=request)
            expense.save()
            log_action(action="entity_created", entity_type="expense",
                       entity_id=expense.pk,
                       diff=snapshot(expense, APPROVAL_FIELDS + ["attachment"]),
                       request=request)
            messages.success(
                request,
                f"سُجِّل المصروف {expense.expense_number} بمبلغ "
                f"{expense.amount} {expense.currency} وسُجِّل في سجل التدقيق.")
            return redirect("expenses:detail", pk=expense.pk)
    else:
        form = forms.ExpenseForm()
    return render(request, "expenses/form.html", {
        "form": form, "is_create": True, "title": "مصروف فعلي جديد",
        "cancel_url": reverse("expenses:list"),
    })


@require_permission("expenses.edit")
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    before = snapshot(expense, APPROVAL_FIELDS + ["attachment"])
    if request.method == "POST":
        form = forms.ExpenseForm(request.POST, request.FILES, instance=expense)
        if form.is_valid():
            original_ref = before.get("approval_reference") or ""
            expense = form.save(commit=False)
            expense.updated_by = request.user
            _apply_approval(expense, form.cleaned_data.get("approval_reference"),
                            original_ref, request.user)
            require_period_postable(
                request.user, expense.period,
                purpose=f"تعديل مصروف {expense.expense_number}", request=request)
            expense.save()
            diff = changes_between(expense, before)
            if diff:
                log_action(action="entity_updated", entity_type="expense",
                           entity_id=expense.pk, diff=diff, request=request)
                messages.success(request,
                                 f"عُدّل المصروف {expense.expense_number} — "
                                 "الفروق مُسجَّلة في سجل التدقيق.")
            else:
                messages.info(request, "لا توجد تغييرات لحفظها.")
            return redirect("expenses:detail", pk=expense.pk)
    else:
        form = forms.ExpenseForm(instance=expense)
    return render(request, "expenses/form.html", {
        "form": form, "is_create": False,
        "title": f"تعديل: {expense.expense_number}",
        "cancel_url": reverse("expenses:detail", args=[expense.pk]),
    })


# ---------------------------------------------------------------- detail + attachment
def expense_detail(request, pk):
    expense = get_object_or_404(Expense.objects.select_related(
        "period__fiscal_year", "department", "account", "expense_category",
        "supplier", "created_by", "updated_by", "approved_by"), pk=pk)
    budget_ctx = services.expense_budget_context(expense)
    audit_rows = []
    if has_perm(request.user, "audittrail.view"):
        audit_rows = AuditLog.objects.filter(
            entity_type="expense", entity_id=str(expense.pk))[:15]
    return render(request, "expenses/detail.html", {
        "e": expense, "budget_ctx": budget_ctx,
        "audit_rows": audit_rows,
        "can_trail": has_perm(request.user, "audittrail.view"),
        "can_edit": has_perm(request.user, "expenses.edit"),
        "edit_url": reverse("expenses:edit", args=[expense.pk]),
        "attachment_url": reverse("expenses:attachment", args=[expense.pk]),
    })


@require_permission("expenses.view")
def expense_attachment(request, pk):
    """Authenticated, audited file access (media is never public here)."""
    expense = get_object_or_404(Expense, pk=pk)
    if not expense.attachment:
        messages.info(request, "لا يوجد مستند مرفق لهذا المصروف.")
        return redirect("expenses:detail", pk=pk)
    log_action(action="expense_attachment_viewed", entity_type="expense",
               entity_id=expense.pk,
               diff={"file": expense.attachment.name,
                     "expense_number": expense.expense_number},
               request=request)
    content_type = (mimetypes.guess_type(expense.attachment.name)[0]
                    or "application/octet-stream")
    response = FileResponse(expense.attachment.open("rb"), content_type=content_type)
    response["Content-Disposition"] = (
        f'inline; filename="{expense.expense_number}"')
    return response


# ---------------------------------------------------------------- export
EXPORT_COLUMNS = [
    ("expense_number", "رقم المصروف"), ("expense_date", "التاريخ"),
    ("period", "الفترة"), ("department", "الإدارة"),
    ("account", "الحساب"), ("expense_category", "التصنيف"),
    ("supplier", "المورّد"), ("description", "البيان"),
    ("amount", "المبلغ"), ("currency", "العملة"),
    ("payment_method", "طريقة الدفع"), ("payment_reference", "مرجع الدفع"),
    ("invoice_reference", "مرجع الفاتورة"),
    ("approval_reference", "مرجع الاعتماد"), ("created_by", "أُنشئ بواسطة"),
]


@require_permission("expenses.view")
def expense_export(request):
    """CSV (UTF-8 BOM — Excel-friendly) of the CURRENT search+filters."""
    qs, _ = _filtered(request)
    count = qs.count()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="expenses-{timezone.now():%Y%m%d-%H%M}.csv"')
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow([label for _, label in EXPORT_COLUMNS])
    for e in qs.iterator():
        values = [
            e.expense_number, e.expense_date.isoformat(), str(e.period),
            str(e.department), str(e.account),
            str(e.expense_category) if e.expense_category_id else "",
            str(e.supplier) if e.supplier_id else "",
            e.description, str(e.amount), e.currency,
            e.get_payment_method_display(), e.payment_reference,
            e.invoice_reference or "", e.approval_reference or "",
            e.created_by.username if e.created_by_id else "",
        ]
        writer.writerow([safe_spreadsheet_value(value) for value in values])
    log_action(action="expenses_exported", entity_type="expense",
               entity_id="",
               diff={"count": count,
                     "filters": {k: v for k, v in request.GET.items() if v}},
               request=request)
    return response
