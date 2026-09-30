"""PHASE 7 services — numbering + the audit-test data contract.

`procurement_audit_context(record)` returns EXACTLY the facts the future
procurement audit tests need (extensible without touching the UI):

    has_po · has_approval · quote_count · lowest_quote · has_attachment ·
    supplier info · amount · date · account/category · status ·
    cancelled flag …
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Min

from apps.reference.models import FiscalYear

from .models import Procurement, Quotation


def next_procurement_number(date) -> str:
    """PR-{year}-{seq:05d} driven by the DB."""
    fy = (
        FiscalYear.objects.filter(
            start_date__lte=date, end_date__gte=date)
        .order_by("-year").first()
    )
    year = fy.year if fy else date.year
    prefix = f"PR-{year}-"
    last = (
        Procurement.objects.filter(reference_number__startswith=prefix)
        .order_by("-reference_number")
        .values_list("reference_number", flat=True).first()
    )
    seq = 1
    if last:
        try:
            seq = int(last.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            seq = Procurement.objects.filter(
                reference_number__startswith=prefix).count() + 1
    return f"{prefix}{seq:05d}"


def procurement_audit_context(record: Procurement) -> dict:
    """Single source of truth for procurement audit tests (extensible)."""
    quotes = record.quotations.select_related("supplier")
    quote_count = quotes.count()
    lowest = quotes.aggregate(v=Min("amount"))["v"]
    return {
        "reference_number": record.reference_number,
        "date": record.date,
        "status": record.status,
        "is_cancelled": record.status == "cancelled",
        "supplier": {
            "code": record.supplier.code,
            "name": record.supplier.name,
            "tax_number": record.supplier.tax_number,
            "email": record.supplier.email,
            "is_active": record.supplier.is_active,
        },
        "amount": record.amount,
        "department": str(record.department),
        "account": str(record.account),
        "account_type": record.account.account_type,
        "category": str(record.expense_category) if record.expense_category_id else None,
        "has_po": record.has_po,
        "po_reference": record.purchase_order or "",
        "has_approval": record.has_approval,
        "approval_reference": record.approval_reference or "",
        "approved_by": record.approved_by.username if record.approved_by_id else None,
        "approved_at": record.approved_at.isoformat() if record.approved_at else None,
        "quote_count": quote_count,
        "lowest_quote": lowest,
        "quotes": [
            {"supplier": q.supplier.code, "amount": q.amount,
             "offer_date": q.offer_date, "reference": q.reference}
            for q in quotes
        ],
        "has_attachment": record.has_attachment,
        "attachment": record.attachment.name if record.has_attachment else "",
        "payment_method": record.payment_method,
        "payment_reference": record.payment_reference or "",
    }
