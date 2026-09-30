"""PHASE 6 services — expense numbering + live budget linkage."""
from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.budget import services as budget_services
from apps.reference.models import FiscalYear, MonthlyPeriod

from .models import Expense


def next_expense_number(expense_date) -> str:
    """EXP-{year}-{seq:05d} for the expense's fiscal year (DB-driven)."""
    fy = (
        FiscalYear.objects.filter(
            start_date__lte=expense_date, end_date__gte=expense_date
        )
        .order_by("-year")
        .first()
    )
    year = fy.year if fy else expense_date.year
    prefix = f"EXP-{year}-"
    last = (
        Expense.objects.filter(expense_number__startswith=prefix)
        .order_by("-expense_number")
        .values_list("expense_number", flat=True)
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            seq = Expense.objects.filter(
                expense_number__startswith=prefix).count() + 1
    return f"{prefix}{seq:05d}"


def period_for_date(expense_date) -> MonthlyPeriod | None:
    """Open-period convenience lookup used by the entry form."""
    return (
        MonthlyPeriod.objects.filter(
            start_date__lte=expense_date, end_date__gte=expense_date,
            is_active=True, status=MonthlyPeriod.STATUS_OPEN,
        )
        .select_related("fiscal_year")
        .order_by("fiscal_year__year", "month")
        .first()
    )


def expense_budget_context(expense) -> dict:
    """BUDGET LINKAGE — live, never stored (analysis-version dependent).

    Returns the analysis version + its line for (dept, account) + the
    line's monthly budget for the expense's period month. This is the
    Budget-vs-Actual join point for a single expense.
    """
    fy = expense.period.fiscal_year
    budget = getattr(fy, "budget", None)
    if budget is None:
        return {"budget": None, "analysis_version": None,
                "line": None, "budgeted": False,
                "monthly_budget": None, "reason": "لا توجد ميزانية لهذه السنة."}
    version = budget_services.get_analysis_version(budget)
    if version is None:
        return {"budget": budget, "analysis_version": None,
                "line": None, "budgeted": False, "monthly_budget": None,
                "reason": "لا توجد نسخة ميزانية معتمدة بعد."}
    line = budget_services.line_for(
        version, expense.department, expense.account)
    month_field = f"m{expense.expense_date.month:02d}"
    monthly = getattr(line, month_field) if line else None
    return {
        "budget": budget,
        "analysis_version": version,
        "line": line,
        "budgeted": line is not None,
        "monthly_budget": monthly,
        "reason": "" if line is not None else
        "خارج الميزانية: لا سطر ميزانية لهذه الإدارة+الحساب في النسخة المعتمدة.",
    }
