"""PHASE 7 — Procurement views (CRUD + quotes + attachment + audit).

Sensitivity: entity_created/updated/deleted for records AND quotations
(diff before/after), attachment view audited. Page/action gates come from
URL_PERMISSIONS (procurement.view / procurement.edit).
"""
from __future__ import annotations

import mimetypes

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q, Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import has_perm, require_permission
from apps.governance.models import AuditLog
from apps.reference.services import changes_between, log_action, snapshot

from . import forms, services
from .models import Procurement, Quotation

RECORD_FIELDS = [
    "reference_number", "date", "department", "supplier", "account",
    "analytical_account", "expense_category", "description", "amount", "status", "purchase_order",
    "approval_reference", "approved_by", "approved_at", "payment_method",
    "payment_reference", "attachment", "notes",
]
QUOTE_FIELDS = ["supplier", "amount", "offer_date", "reference", "notes"]


# ---------------------------------------------------------------- shared
def _filtered(request):
    qs = Procurement.objects.select_related(
        "department", "supplier", "account", "analytical_account",
        "expense_category", "created_by")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(reference_number__icontains=q)
            | Q(description__icontains=q)
            | Q(purchase_order__icontains=q)
            | Q(payment_reference__icontains=q)
            | Q(supplier__name__icontains=q)
            | Q(supplier__code__icontains=q)
        )
    status = (request.GET.get("status") or "").strip()
    valid_statuses = {c[0] for c in Procurement.STATUS_CHOICES}
    if status in valid_statuses:
        qs = qs.filter(status=status)
    for param, lookup in (("department", "department_id"),
                          ("supplier", "supplier_id"),
                          ("account", "account_id"),
                          ("analytical_account", "analytical_account_id"),
                          ("category", "expense_category_id")):
        raw = (request.GET.get(param) or "").strip()
        if raw.isdigit():
            qs = qs.filter(**{lookup: int(raw)})
    has_po = (request.GET.get("has_po") or "").strip()
    if has_po == "yes":
        qs = qs.exclude(purchase_order="")
    elif has_po == "no":
        qs = qs.filter(purchase_order="")
    has_approval = (request.GET.get("has_approval") or "").strip()
    if has_approval == "yes":
        qs = qs.exclude(approval_reference="").exclude(
            approval_reference__isnull=True)
    elif has_approval == "no":
        qs = qs.filter(Q(approval_reference="") |
                       Q(approval_reference__isnull=True))
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    return qs, q


def _filter_context(request) -> dict:
    from apps.reference.models import Department, ExpenseCategory, Account, Supplier
    return {
        "filter_options": {
            "departments": Department.objects.filter(is_active=True),
            "suppliers": Supplier.objects.filter(is_active=True),
            "accounts": Account.objects.main_accounts().filter(account_type="expense"),
            "analytical_accounts": Account.objects.analytical_accounts().filter(
                account_type="expense",
            ),
            "categories": ExpenseCategory.objects.filter(is_active=True),
            "statuses": Procurement.STATUS_CHOICES,
            "yesno": [("", "الكل"), ("yes", "موجود"), ("no", "غائب")],
        },
        "sel": {k: (request.GET.get(k) or "")
                for k in ("status", "department", "supplier", "account", "analytical_account",
                          "category", "has_po", "has_approval",
                          "date_from", "date_to")},
    }


# ---------------------------------------------------------------- list
def procurement_list(request):
    qs, q = _filtered(request)
    filtered_total = qs.aggregate(total=Sum("amount"))["total"]
    paginator = Paginator(qs, 15)
    try:
        page = paginator.get_page(request.GET.get("page"))
    except PageNotAnInteger:
        page = paginator.get_page(1)
    except EmptyPage:
        page = paginator.get_page(paginator.num_pages)
    return render(request, "procurement/list.html", {
        "rows": page, "q": q, "total": paginator.count,
        "filtered_total": filtered_total, "page_obj": page,
        "can_edit": has_perm(request.user, "procurement.edit"),
        "create_url": reverse("procurement:create"),
        **_filter_context(request),
    })


# ---------------------------------------------------------------- record CRUD
@require_permission("procurement.edit")
def procurement_create(request):
    if request.method == "POST":
        form = forms.ProcurementForm(request.POST, request.FILES)
        if form.is_valid():
            record = form.save(commit=False)
            if not record.reference_number:
                record.reference_number = services.next_procurement_number(
                    record.date)
            _apply_approval(record, form.cleaned_data.get("approval_reference"),
                            "", request.user)
            record.created_by = request.user
            record.updated_by = request.user
            record.save()
            log_action(action="entity_created", entity_type="procurement",
                       entity_id=record.pk,
                       diff=snapshot(record, RECORD_FIELDS), request=request)
            messages.success(
                request,
                f"أُنشئ السجل {record.reference_number} وسُجِّل في سجل التدقيق.")
            return redirect("procurement:detail", pk=record.pk)
    else:
        form = forms.ProcurementForm()
    return render(request, "procurement/form.html", {
        "form": form, "is_create": True, "title": "سجل مشتريات جديد",
        "cancel_url": reverse("procurement:list"),
    })


def _apply_approval(record, ref, original_ref, user):
    """A NEW reference stamps approver/time; clearing resets them."""
    ref = (ref or "").strip()
    if ref and (ref != original_ref or record.approved_by_id is None):
        record.approved_by = user
        record.approved_at = timezone.now()
    elif not ref and original_ref:
        record.approved_by = None
        record.approved_at = None
    record.approval_reference = ref


def procurement_detail(request, pk):
    record = get_object_or_404(Procurement.objects.select_related(
        "department", "supplier", "account", "analytical_account", "expense_category",
        "created_by", "updated_by", "approved_by"), pk=pk)
    audit_ctx = services.procurement_audit_context(record)
    quotes = list(record.quotations.select_related("supplier"))
    audit_rows = []
    if has_perm(request.user, "audittrail.view"):
        audit_rows = AuditLog.objects.filter(
            entity_type="procurement", entity_id=str(record.pk))[:15]
    return render(request, "procurement/detail.html", {
        "p": record, "audit_ctx": audit_ctx, "quotes": quotes,
        "audit_rows": audit_rows,
        "can_trail": has_perm(request.user, "audittrail.view"),
        "can_edit": has_perm(request.user, "procurement.edit"),
        "edit_url": reverse("procurement:edit", args=[record.pk]),
        "delete_url": reverse("procurement:delete", args=[record.pk]),
        "attachment_url": reverse("procurement:attachment", args=[record.pk]),
        "quote_create_url": reverse("procurement:quote_create",
                                    args=[record.pk]),
    })


@require_permission("procurement.edit")
def procurement_edit(request, pk):
    record = get_object_or_404(Procurement, pk=pk)
    before = snapshot(record, RECORD_FIELDS)
    if request.method == "POST":
        form = forms.ProcurementForm(request.POST, request.FILES, instance=record)
        if form.is_valid():
            original_ref = before.get("approval_reference") or ""
            record = form.save(commit=False)
            record.updated_by = request.user
            _apply_approval(record, form.cleaned_data.get("approval_reference"),
                            original_ref, request.user)
            record.save()
            diff = changes_between(record, before)
            if diff:
                log_action(action="entity_updated", entity_type="procurement",
                           entity_id=record.pk, diff=diff, request=request)
                messages.success(request,
                                 f"عُدّل السجل {record.reference_number} — "
                                 "الفروق مُسجَّلة.")
            else:
                messages.info(request, "لا توجد تغييرات لحفظها.")
            return redirect("procurement:detail", pk=record.pk)
    else:
        form = forms.ProcurementForm(instance=record)
    return render(request, "procurement/form.html", {
        "form": form, "is_create": False,
        "title": f"تعديل: {record.reference_number}",
        "cancel_url": reverse("procurement:detail", args=[record.pk]),
    })


@require_permission("procurement.edit")
def procurement_delete(request, pk):
    record = get_object_or_404(Procurement, pk=pk)
    if request.method != "POST":
        messages.error(request, "الحذف يتطلب تأكيدًا (POST).")
        return redirect("procurement:detail", pk=pk)
    if record.status not in ("draft", "cancelled"):
        messages.error(
            request,
            "لا يمكن حذف سجل مشتريات بحالة "
            f"«{record.get_status_display()}» — ألغِه (status = ملغى) أو "
            "اتركه لأغراض التدقيق.",
        )
        return redirect("procurement:detail", pk=pk)
    before = snapshot(record, RECORD_FIELDS)
    label, num = str(record), record.reference_number
    record.delete()
    log_action(action="entity_deleted", entity_type="procurement",
               entity_id=pk, diff={"snapshot": before, "label": label},
               request=request)
    messages.success(request, f"حُذف السجل «{label}» وسُجِّل في سجل التدقيق.")
    return redirect("procurement:list")


# ---------------------------------------------------------------- quotes (CRUD)
@require_permission("procurement.edit")
def quote_create(request, pk):
    record = get_object_or_404(Procurement, pk=pk)
    if request.method == "POST":
        form = forms.QuotationForm(request.POST, procurement=record)
        if form.is_valid():
            quote = form.save(commit=False)
            quote.procurement = record
            quote.save()
            log_action(action="entity_created", entity_type="quotation",
                       entity_id=quote.pk,
                       diff={"procurement": record.reference_number,
                             **snapshot(quote, QUOTE_FIELDS)},
                       request=request)
            messages.success(request,
                             f"أُضيف عرض {quote.supplier.code} وسُجِّل في سجل التدقيق.")
            return redirect("procurement:detail", pk=record.pk)
    else:
        form = forms.QuotationForm(procurement=record)
    return render(request, "procurement/quote_form.html", {
        "form": form, "p": record, "is_create": True,
        "title": f"عرض مورّد جديد — {record.reference_number}",
        "cancel_url": reverse("procurement:detail", args=[record.pk]),
    })


@require_permission("procurement.edit")
def quote_edit(request, pk):
    quote = get_object_or_404(Quotation.objects.select_related("procurement"),
                              pk=pk)
    record = quote.procurement
    before = snapshot(quote, QUOTE_FIELDS)
    if request.method == "POST":
        form = forms.QuotationForm(request.POST, procurement=record,
                                   instance=quote)
        if form.is_valid():
            quote = form.save()
            diff = changes_between(quote, before)
            if diff:
                log_action(action="entity_updated", entity_type="quotation",
                           entity_id=quote.pk, diff=diff, request=request)
                messages.success(request, "عُدّل العرض وسُجَّلت الفروق.")
            return redirect("procurement:detail", pk=record.pk)
    else:
        form = forms.QuotationForm(procurement=record, instance=quote)
    return render(request, "procurement/quote_form.html", {
        "form": form, "p": record, "is_create": False,
        "title": f"تعديل عرض — {quote.supplier.code}",
        "cancel_url": reverse("procurement:detail", args=[record.pk]),
    })


@require_permission("procurement.edit")
def quote_delete(request, pk):
    quote = get_object_or_404(Quotation.objects.select_related("procurement"),
                              pk=pk)
    record = quote.procurement
    if request.method != "POST":
        messages.error(request, "الحذف يتطلب تأكيدًا (POST).")
        return redirect("procurement:detail", pk=record.pk)
    before = snapshot(quote, QUOTE_FIELDS)
    label, quote_pk = str(quote), quote.pk
    quote.delete()
    log_action(action="entity_deleted", entity_type="quotation",
               entity_id=quote_pk,
               diff={"snapshot": before, "label": label,
                     "procurement": record.reference_number},
               request=request)
    messages.success(request, f"حُذف العرض «{label}» وسُجِّل في سجل التدقيق.")
    return redirect("procurement:detail", pk=record.pk)


# ---------------------------------------------------------------- attachment
@require_permission("procurement.view")
def procurement_attachment(request, pk):
    record = get_object_or_404(Procurement, pk=pk)
    if not record.attachment:
        messages.info(request, "لا يوجد مستند مرفق لهذا السجل.")
        return redirect("procurement:detail", pk=pk)
    log_action(action="procurement_attachment_viewed",
               entity_type="procurement",
               entity_id=record.pk,
               diff={"file": record.attachment.name,
                     "reference_number": record.reference_number},
               request=request)
    content_type = (mimetypes.guess_type(record.attachment.name)[0]
                    or "application/octet-stream")
    response = FileResponse(record.attachment.open("rb"),
                            content_type=content_type)
    response["Content-Disposition"] = (
        f'inline; filename="{record.reference_number}"')
    return response
