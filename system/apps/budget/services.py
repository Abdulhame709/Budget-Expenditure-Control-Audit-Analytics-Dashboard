"""PHASE 5 services — DB-computed budget analytics foundation.

Everything below reads from PostgreSQL aggregates (no hardcoded numbers).
These are the building blocks the later phases will use for:
    Budget vs Actual · Variance · Out-of-Budget
(actuals arrive with the expenses module; this phase ships the budget
side of the contract + tests).
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from .models import MONTH_FIELDS, Budget, BudgetLine, BudgetVersion

ZERO = Decimal("0")


def get_analysis_version(budget: Budget) -> BudgetVersion | None:
    """The single version analysis must use: latest APPROVED (else None)."""
    return budget.versions.filter(
        status=BudgetVersion.STATUS_APPROVED
    ).order_by("-version").first()


def version_totals(version: BudgetVersion) -> dict:
    """Aggregates straight from the DB for one budget version."""
    agg = version.lines.aggregate(
        annual=Sum("annual_amount"),
        **{f: Sum(f) for f in MONTH_FIELDS},
    )
    return {
        "annual_total": agg["annual"] or ZERO,
        "monthly": [agg[f] or ZERO for f in MONTH_FIELDS],
        "line_count": version.lines.count(),
    }


def totals_by(version: BudgetVersion, field: str) -> list[dict]:
    """Grouped totals: field ∈ department | account | expense_category."""
    rows = (
        version.lines.values(field)
        .annotate(total=Sum("annual_amount"))
        .order_by(field)
    )
    # attach readable labels (still DB-driven)
    if field == "department":
        from apps.reference.models import Department
        labels = {o.pk: str(o) for o in Department.objects.filter(
            pk__in=[r[field] for r in rows])}
    elif field == "account":
        from apps.reference.models import Account
        labels = {o.pk: str(o) for o in Account.objects.filter(
            pk__in=[r[field] for r in rows])}
    else:
        from apps.reference.models import ExpenseCategory
        labels = {o.pk: str(o) for o in ExpenseCategory.objects.filter(
            pk__in=[r[field] for r in rows])}
    return [
        {"key": r[field], "label": labels.get(r[field], "—"),
         "total": r["total"] or ZERO}
        for r in rows
    ]


def monthly_budget_map(version: BudgetVersion) -> dict:
    """VARIANCE FOUNDATION: lookup[(department_id, account_id)] =
    {'monthly': [12 amounts], 'annual': …, 'line_id': …}."""
    result = {}
    for line in version.lines.all():
        result[(line.department_id, line.account_id)] = {
            "monthly": [getattr(line, f) or ZERO for f in MONTH_FIELDS],
            "annual": line.annual_amount,
            "line_id": line.pk,
            "category_id": line.expense_category_id,
        }
    return result


def is_budgeted(version: BudgetVersion, department, account) -> bool:
    """OUT-OF-BUDGET FOUNDATION: does this (dept, account) have budget
    coverage in the analysis version? An expense without coverage is an
    out-of-budget candidate (actual check happens in a later phase)."""
    return version.lines.filter(
        department=department, account=account
    ).exists()


def line_for(version: BudgetVersion, department, account) -> BudgetLine | None:
    """Exact budget line for a (dept, account) pair — used by future
    Budget-vs-Actual/Variance computations at line level."""
    return version.lines.filter(
        department=department, account=account
    ).first()
