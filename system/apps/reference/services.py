"""PHASE 4 services — audit logging + the closed-period posting rule.

Closed-period rule (user requirement):
    «لا تسمح بإدخال معاملات في Period مغلق إلا وفق صلاحية محددة
      ومسجلة في Audit Trail»
→ every future transaction module MUST call `require_period_postable()`
  before saving into a period; bypass raises PermissionDenied unless the
  actor holds `periods.post_closed`, and every allowed override is
  written to the Audit Trail (action=closed_period_override).
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import PermissionDenied

from apps.accounts.permissions import PERMISSIONS, has_perm
from apps.governance.services import log_action

# fields included in create/update/delete audit snapshots (per model defaults)
SNAPSHOT_FIELDS = {
    "fiscalyear": ["code", "name", "year", "start_date", "end_date", "is_active"],
    "monthlyperiod": ["fiscal_year", "month", "start_date", "end_date", "status", "is_active"],
    "department": ["code", "name", "parent", "is_active"],
    "employee": [
        "code", "full_name", "department", "cost_center", "job_title",
        "contract_type", "start_date", "end_date", "is_active",
    ],
    "expensecategory": ["code", "name", "is_active"],
    "account": ["code", "name", "account_type", "parent", "expense_category", "is_active"],
    "supplier": ["code", "name", "contact_person", "phone", "email", "tax_number", "is_active"],
}


def snapshot(obj, fields: list[str] | None = None) -> dict:
    """JSON-safe snapshot of the given (or model-default) fields."""
    model_key = obj._meta.model_name
    fields = fields or SNAPSHOT_FIELDS.get(model_key) or [
        f.name for f in obj._meta.fields if not f.auto_created
    ]
    out = {}
    for name in fields:
        value = getattr(obj, name, None)
        if hasattr(value, "pk"):          # FK → readable label
            value = str(value)
        elif hasattr(value, "isoformat"):  # dates/datetimes
            value = value.isoformat()
        elif isinstance(value, Decimal):   # money → exact string, never float
            value = str(value)
        elif isinstance(value, bool):
            value = bool(value)
        elif value is not None and not isinstance(value, (str, int, float)):
            value = str(value)             # FieldFile etc. → safe string
        out[name] = value
    return out


def log_reference_action(action: str, obj, diff: dict, request=None) -> None:
    """One wrapper so every module logs with the same shape."""
    log_action(
        action=action,
        entity_type=obj._meta.model_name,
        entity_id=obj.pk,
        diff=diff,
        request=request,
    )


def changes_between(obj, before: dict) -> dict:
    """Only the fields that actually changed (before → after)."""
    after = snapshot(obj, list(before))
    return {
        k: {"before": before.get(k), "after": after.get(k)}
        for k in after
        if before.get(k) != after.get(k)
    }


def require_period_postable(user, period, *, purpose: str = "", request=None) -> None:
    """The single enforcement point for the closed-period rule.

    Raises PermissionDenied when the period is unusable and the actor
    lacks `periods.post_closed`. Allowed overrides are always audited.
    """
    problems = []
    if period.is_closed:
        problems.append("الفترة الشهرية مغلقة")
    if not period.is_active:
        problems.append("الفترة غير نشطة")
    if not period.fiscal_year.is_active:
        problems.append("السنة المالية غير نشطة")
    if not problems:
        return  # normal path — open & active, nothing to audit

    if not has_perm(user, "periods.post_closed"):
        code, label = PERMISSIONS["periods.post_closed"]
        raise PermissionDenied(
            "لا يُسمح بالتسجيل معاملات في فترة "
            + " و".join(problems)
            + f" — يتطلب صلاحية «{label}» ({code})."
        )

    # permission held → allow, but ALWAYS record the override in the Audit Trail
    log_action(
        action="closed_period_override",
        entity_type="monthly_period",
        entity_id=period.pk,
        diff={
            "purpose": purpose[:200],
            "reasons": problems,
            "period": str(period),
            "period_status": period.status,
            "is_active": period.is_active,
            "fiscal_year_active": period.fiscal_year.is_active,
        },
        request=request,
        actor=user,
    )
