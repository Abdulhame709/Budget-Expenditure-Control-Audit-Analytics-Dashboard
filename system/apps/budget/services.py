"""PHASE 5 services — DB-computed budget analytics foundation.

Everything below reads from PostgreSQL aggregates (no hardcoded numbers).
These are the building blocks the later phases will use for:
    Budget vs Actual · Variance · Out-of-Budget
(actuals arrive with the expenses module; this phase ships the budget
side of the contract + tests).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import (
    MONTH_FIELDS,
    Budget,
    BudgetLine,
    BudgetPlan,
    BudgetPlanLine,
    BudgetPlanPeriodAmount,
    BudgetVersion,
)

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


def is_budgeted(
    version: BudgetVersion, department, account, analytical_account=None,
) -> bool:
    """OUT-OF-BUDGET FOUNDATION: does this (dept, account) have budget
    coverage in the analysis version? An expense without coverage is an
    out-of-budget candidate (actual check happens in a later phase)."""
    rows = version.lines.filter(department=department, account=account)
    if analytical_account is not None:
        rows = rows.filter(analytical_account=analytical_account)
    return rows.exists()


def line_for(
    version: BudgetVersion, department, account, analytical_account=None,
) -> BudgetLine | None:
    """Exact budget line for department + main account + analytical account."""
    rows = version.lines.filter(department=department, account=account)
    if analytical_account is not None:
        exact = rows.filter(analytical_account=analytical_account).first()
        if exact is not None:
            return exact
        return rows.filter(analytical_account__isnull=True).first()
    return rows.first()


CENT = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_plan_line_annual(
    line: BudgetPlanLine, monthly_values: dict[int, Decimal] | None = None,
) -> Decimal:
    """احسب إجمالي البند من طريقة الإدخال دون الاعتماد على العرض."""
    if line.input_mode == BudgetPlanLine.INPUT_NONE:
        return ZERO
    if line.input_mode == BudgetPlanLine.INPUT_ANNUAL:
        return _money(line.annual_amount)
    if line.input_mode == BudgetPlanLine.INPUT_MONTHLY:
        values = monthly_values or {
            row.month: row.amount for row in line.period_amounts.all()
        }
        return _money(sum((_money(values.get(month, ZERO)) for month in range(1, 13)), ZERO))
    if line.input_mode == BudgetPlanLine.INPUT_QUANTITY_PRICE:
        return _money(Decimal(line.quantity or 0) * Decimal(line.unit_price or 0))
    if line.input_mode == BudgetPlanLine.INPUT_PERIODIC:
        return _money(Decimal(line.periodic_amount or 0) * Decimal(line.periods_count or 0))
    raise ValidationError({"input_mode": "طريقة الإدخال غير مدعومة."})


def distribute_plan_line(
    line: BudgetPlanLine,
    annual_amount: Decimal,
    manual_values: dict[int, Decimal] | None = None,
) -> dict[int, Decimal]:
    """وزّع الإجمالي على 12 شهرًا مع وضع فرق التقريب في آخر شهر مستخدم."""
    annual_amount = _money(annual_amount)
    empty = {month: ZERO for month in range(1, 13)}
    method = line.distribution_method

    if line.input_mode == BudgetPlanLine.INPUT_MONTHLY or method == BudgetPlanLine.DIST_MANUAL:
        values = {
            month: _money((manual_values or {}).get(month, ZERO))
            for month in range(1, 13)
        }
        if _money(sum(values.values(), ZERO)) != annual_amount:
            raise ValidationError({
                "annual_amount": "مجموع مبالغ الأشهر يجب أن يساوي المبلغ السنوي."
            })
        return values
    if method == BudgetPlanLine.DIST_NONE:
        if annual_amount != ZERO:
            raise ValidationError({
                "distribution_method": "اختر طريقة توزيع للمبلغ السنوي."
            })
        return empty
    if method == BudgetPlanLine.DIST_SINGLE_MONTH:
        empty[line.single_month] = annual_amount
        return empty
    if method == BudgetPlanLine.DIST_SELECTED_MONTHS:
        months = sorted(set(line.selected_months or []))
    else:
        months = list(range(1, 13))

    if not months:
        raise ValidationError({"selected_months": "اختر شهرًا واحدًا على الأقل."})
    share = (annual_amount / len(months)).quantize(CENT, rounding=ROUND_HALF_UP)
    values = dict(empty)
    for month in months:
        values[month] = share
    values[months[-1]] += annual_amount - sum(values.values(), ZERO)
    return values


@transaction.atomic
def sync_plan_line_amounts(
    line: BudgetPlanLine, manual_values: dict[int, Decimal] | None = None,
) -> dict[int, Decimal]:
    annual_amount = calculate_plan_line_annual(line, manual_values)
    values = distribute_plan_line(line, annual_amount, manual_values)
    if line.annual_amount != annual_amount:
        line.annual_amount = annual_amount
        line.save(update_fields=["annual_amount", "updated_at"])
    for month, amount in values.items():
        BudgetPlanPeriodAmount.objects.update_or_create(
            line=line, month=month, defaults={"amount": amount},
        )
    return values


def _plan_input_lines(plan: BudgetPlan):
    return BudgetPlanLine.objects.filter(
        section__plan=plan,
        is_included=True,
    ).exclude(input_mode=BudgetPlanLine.INPUT_NONE).select_related(
        "section", "main_account", "analytical_account", "department", "employee"
    ).prefetch_related("period_amounts")


def detailed_plan_output(plan: BudgetPlan) -> list[dict]:
    """المخرج التفصيلي: كل الأقسام والصفوف مع المبالغ الشهرية إن وجدت."""
    result = []
    for section in plan.sections.select_related("department").prefetch_related(
        "lines__period_amounts",
    ).all():
        lines = []
        for line in section.lines.select_related(
            "main_account", "analytical_account", "department", "employee"
        ).prefetch_related("aggregate_sections").all():
            month_map = {row.month: row.amount for row in line.period_amounts.all()}
            annual_amount = line.annual_amount
            if line.input_mode == BudgetPlanLine.INPUT_NONE and line.aggregate_sections.exists():
                aggregate_ids = line.aggregate_sections.values_list("pk", flat=True)
                source_lines = _plan_input_lines(plan).filter(section_id__in=aggregate_ids)
                month_map = {month: ZERO for month in range(1, 13)}
                annual_amount = ZERO
                for source in source_lines:
                    annual_amount += source.annual_amount
                    for period in source.period_amounts.all():
                        month_map[period.month] += period.amount
            lines.append({
                "line": line,
                "monthly": [month_map.get(month, ZERO) for month in range(1, 13)],
                "annual_amount": annual_amount,
            })
        result.append({"section": section, "lines": lines})
    return result


def monthly_plan_output(plan: BudgetPlan) -> list[dict]:
    """المخرج الشهري التفصيلي مجمّعًا حسب الحساب الرئيسي والتحليلي."""
    grouped: dict[tuple[int | None, int | None], dict] = {}
    for line in _plan_input_lines(plan):
        key = (line.main_account_id, line.analytical_account_id)
        row = grouped.setdefault(key, {
            "main_account": line.main_account,
            "analytical_account": line.analytical_account,
            "monthly": [ZERO] * 12,
            "annual_total": ZERO,
        })
        for amount in line.period_amounts.all():
            row["monthly"][amount.month - 1] += amount.amount
        row["annual_total"] += line.annual_amount
    return sorted(
        grouped.values(),
        key=lambda row: (
            row["main_account"].code if row["main_account"] else "",
            row["analytical_account"].code if row["analytical_account"] else "",
        ),
    )


def summary_plan_output(plan: BudgetPlan) -> list[dict]:
    """المخرج الإجمالي الشهري للحسابات الرئيسية فقط."""
    grouped: dict[int | None, dict] = {}
    for line in _plan_input_lines(plan):
        key = line.main_account_id
        row = grouped.setdefault(key, {
            "main_account": line.main_account,
            "monthly": [ZERO] * 12,
            "annual_total": ZERO,
        })
        for amount in line.period_amounts.all():
            row["monthly"][amount.month - 1] += amount.amount
        row["annual_total"] += line.annual_amount
    return sorted(
        grouped.values(),
        key=lambda row: row["main_account"].code if row["main_account"] else "",
    )
