"""PHASE 11 — لوحة مؤشرات تفاعلية (Dashboard) من استعلامات PostgreSQL حقيقية.

كل رقم في الصفحة يُشتق من استعلام ORM حي وقت الطلب — لا أرقام ثابتة ولا قيم
مدمجة داخل القوالب. منطق تفسيري بسيط فقط (لا AI/ML):
  Effective Budget = مجموع أعمدة الشهور المختارة من سطور الموازنة المعتمدة
  Actual Expenses  = مجموع مصروفات YER (ريال يمني) داخل نافذة التاريخ المختارة
  Variance         = Effective Budget − Actual Expenses
  Utilization %    = Actual / Effective Budget (يُعرض «—» إذا لم توجد موازنة)
  Out-of-Budget    = مصروفات لا توجد تركيبة (إدارة × حساب) معتمدة لها
"""
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.shortcuts import render

from apps.accounts.permissions import require_permission
from apps.audit_register.models import (
    AuditException,
    AuditRun,
    AuditTest,
    AuditTestResult,
)
from apps.budget.models import BudgetLine, BudgetVersion
from apps.expenses.models import Expense
from apps.reference.models import (
    Account,
    Department,
    ExpenseCategory,
    FiscalYear,
    MonthlyPeriod,
)

D = Decimal

MONTHS_AR = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]
RISK_LEVELS = ("High", "Medium", "Low")
STATUS_AR = {"open": "مفتوح", "acknowledged": "مُعتمد", "resolved": "مُعالج"}
RESULT_AR = {"pass": "ناجح", "flagged": "مُعلَّم", "fail": "فاشل"}
MODE_AR = {"single": "اختبار واحد", "selected": "اختبارات مختارة",
          "all_active": "كل الاختبارات المفعّلة"}


def _money(value) -> str:
    return f"{value:,.2f}"


def _read_filters(request) -> dict:
    """قراءة فلاتر الطلب (كلها GET وتعتمد على قيم من قاعدة البيانات)."""
    def int_or_none(raw):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    risk = request.GET.get("risk", "")
    if risk not in RISK_LEVELS:
        risk = ""
    return {
        "period": int_or_none(request.GET.get("period")),
        "department": int_or_none(request.GET.get("department")),
        "account": int_or_none(request.GET.get("account")),
        "category": int_or_none(request.GET.get("category")),
        "risk": risk,
        "test": request.GET.get("test", "").strip(),
    }


def _resolve_window(filters: dict):
    """نافذة التحليل: (months, date_from, date_to, fiscal_year)."""
    fy = FiscalYear.objects.order_by("-year").first()
    if filters["period"]:
        period = MonthlyPeriod.objects.select_related("fiscal_year").filter(
            pk=filters["period"]).first()
        if period:
            return ([period.month], period.start_date, period.end_date,
                    period.fiscal_year)
    if fy:
        return (list(range(1, 13)), fy.start_date, fy.end_date, fy)
    return (list(range(1, 13)), None, None, None)


def _filtered_budget_lines(filters: dict, fiscal_year):
    qs = BudgetLine.objects.filter(version__status="approved")
    if fiscal_year is not None:
        qs = qs.filter(version__budget__fiscal_year=fiscal_year)
    if filters["department"]:
        qs = qs.filter(department_id=filters["department"])
    if filters["account"]:
        qs = qs.filter(account_id=filters["account"])
    if filters["category"]:
        qs = qs.filter(account__expense_category_id=filters["category"])
    return qs.select_related("department", "account")


def _filtered_expenses(filters: dict, date_from, date_to):
    qs = Expense.objects.filter(currency="YER")
    if date_from and date_to:
        qs = qs.filter(expense_date__gte=date_from, expense_date__lte=date_to)
    if filters["department"]:
        qs = qs.filter(department_id=filters["department"])
    if filters["account"]:
        qs = qs.filter(account_id=filters["account"])
    if filters["category"]:
        qs = qs.filter(expense_category_id=filters["category"])
    return qs


def _filtered_exceptions(filters: dict):
    """الاستثناءات تتأثر بفلتري الخطر والاختبار فقط — فلتر الفترة مالي
    (تاريخ رصد الاستثناء ≠ تاريخ المعاملة المالية فلا يُخلط بينهما)."""
    qs = AuditException.objects.all()
    if filters["test"]:
        qs = qs.filter(test_code=filters["test"])
    if filters["risk"]:
        qs = qs.filter(risk_level=filters["risk"])
    return qs


def _effective_budget(budget_qs, months) -> Decimal:
    cols = {f"m{m:02d}": Sum(f"m{m:02d}") for m in months}
    if not cols:
        return D("0")
    agg = budget_qs.aggregate(**cols)
    return sum((agg[c] or D("0")) for c in cols)


def dashboard(request):
    filters = _read_filters(request)
    months, date_from, date_to, fy = _resolve_window(filters)
    budget_qs = _filtered_budget_lines(filters, fy)
    exp_qs = _filtered_expenses(filters, date_from, date_to)
    exc_qs = _filtered_exceptions(filters)

    # ---------------------------------------------------- KPIs (سؤال 1..9)
    eff_budget = _effective_budget(budget_qs, months)
    actual = exp_qs.aggregate(s=Sum("amount"))["s"] or D("0")
    variance = eff_budget - actual
    utilization = (actual / eff_budget * 100) if eff_budget > 0 else None

    # سؤال 5 — المصروفات خارج الموازنة: تركيبة (إدارة×حساب) غير موجودة في
    # أي سطر موازنة معتمد ضمن نفس الفلاتر.
    budget_keys = set(budget_qs.values_list("department_id", "account_id"))
    oob_qs = exp_qs.all()
    oob_total, oob_count = D("0"), 0
    oob_rows = []
    for e in oob_qs.select_related("department", "account"):
        if (e.department_id, e.account_id) in budget_keys:
            continue
        oob_total += e.amount
        oob_count += 1
        if len(oob_rows) < 10:
            oob_rows.append({
                "expense_number": e.expense_number,
                "date": e.expense_date,
                "department": e.department.name,
                "account": e.account.name,
                "amount": e.amount,
            })

    exception_summary = exc_qs.aggregate(
        total=Count("id"),
        high=Count("id", filter=Q(risk_level="High")),
        procurement=Count("id", filter=Q(source_type="procurement")),
    )
    exc_count = exception_summary["total"]
    high_count = exception_summary["high"]
    proc_count = exception_summary["procurement"]

    kpis = {
        "effective_budget": eff_budget,
        "actual": actual,
        "variance": variance,
        "utilization": utilization,
        "oob_amount": oob_total,
        "oob_count": oob_count,
        "exceptions": exc_count,
        "high_risk": high_count,
        "proc_exceptions": proc_count,
    }
    kpis_fmt = {
        "effective_budget": _money(eff_budget),
        "actual": _money(actual),
        "variance": _money(variance),
        "utilization": (f"{utilization:.1f}" if utilization is not None
                        else "—"),
        "oob_amount": _money(oob_total),
        "oob_count": f"{oob_count}",
        "exceptions": f"{exc_count}",
        "high_risk": f"{high_count}",
        "proc_exceptions": f"{proc_count}",
    }

    # ------------------------------------- سؤال 6 — إدارات ذات انحرافات
    dept_budget: dict[int, Decimal] = {}
    dept_budget_name: dict[int, str] = {}
    cols = {f"m{m:02d}": Sum(f"m{m:02d}") for m in months}
    for row in budget_qs.values("department_id", "department__name").annotate(
            **cols):
        total = sum((row[c] or D("0")) for c in cols)
        dept_budget[row["department_id"]] = total
        dept_budget_name[row["department_id"]] = row["department__name"]
    dept_actual: dict[int, Decimal] = {}
    dept_actual_name: dict[int, str] = {}
    for row in exp_qs.values("department_id", "department__name").annotate(
            total=Sum("amount")):
        dept_actual[row["department_id"]] = row["total"] or D("0")
        dept_actual_name[row["department_id"]] = row["department__name"]

    dept_ids = set(dept_budget) | set(dept_actual)
    dept_rows = []
    for did in sorted(dept_ids):
        name = dept_budget_name.get(did) or dept_actual_name.get(did) or "—"
        b = dept_budget.get(did, D("0"))
        a = dept_actual.get(did, D("0"))
        v = b - a
        dept_rows.append({
            "id": did, "name": name, "budget": b, "actual": a,
            "variance": v,
            "utilization": (a / b * 100) if b > 0 else None,
            "has_variance": v != 0,
        })
    dept_rows.sort(key=lambda r: (-abs(r["variance"]), r["name"]))

    # ------------------------------------- سؤال 7 — أعلى الحسابات صرفًا
    top_accounts = [
        {"id": r["account_id"], "name": r["account__name"],
         "total": r["total"] or D("0")}
        for r in exp_qs.values("account_id", "account__name").annotate(
            total=Sum("amount")).order_by("-total")[:8]
    ]

    # ------------------------------------- سؤال 11 — الاتجاه الشهري
    # (سنة الفiscal كاملة لعرض السياق؛ يراعي فلاتر الإدارة/الحساب/التصنيف)
    trend_labels = list(MONTHS_AR)
    month_cols = [f"m{m:02d}" for m in range(1, 13)]
    agg = budget_qs.aggregate(**{c: Sum(c) for c in month_cols})
    trend_budget = [agg[c] or D("0") for c in month_cols]
    trend_actual = [D("0")] * 12
    trend_src = exp_qs
    if fy is not None:
        trend_src = trend_src.filter(expense_date__gte=fy.start_date,
                                     expense_date__lte=fy.end_date)
    for row in trend_src.values_list("expense_date", "amount"):
        m = row[0].month
        if 1 <= m <= 12:
            trend_actual[m - 1] += row[1]

    # ------------------------------------- سؤال 9 — مستويات المخاطر
    risk_counts = OrderedDict(
        (lvl, 0) for lvl in RISK_LEVELS)
    for row in exc_qs.values("risk_level").annotate(n=Count("id")):
        if row["risk_level"] in risk_counts:
            risk_counts[row["risk_level"]] = row["n"]

    # ------------------------------------- سؤال 8 — الاستثناءات
    status_counts = OrderedDict(
        (code, {"label": label, "n": 0})
        for code, label in STATUS_AR.items())
    for row in exc_qs.values("status").annotate(n=Count("id")):
        if row["status"] in status_counts:
            status_counts[row["status"]]["n"] = row["n"]
    recent_exceptions = [
        {"pk": e.pk, "test_code": e.test_code, "title": e.title,
         "risk_level": e.risk_level, "status": e.status,
         "amount": e.amount, "source_type": e.source_type}
        for e in exc_qs.order_by("-detected_at")[:6]
    ]

    # ------------------------------------- سؤال 10 — نتائج Audit Tests
    # آخر جولة ذات نتائج (أو آخر جولة تحتوي الاختبار المختار بالفلتر)
    run_qs = AuditRun.objects.order_by("-pk")
    if filters["test"]:
        run_qs = AuditRun.objects.filter(
            results__test__test_code=filters["test"]).order_by("-pk")
    latest_run = run_qs.first()
    result_rows, result_totals = [], {"pass": 0, "flagged": 0, "fail": 0}
    if latest_run:
        results = AuditTestResult.objects.filter(
            run=latest_run).select_related("test")
        if filters["test"]:
            results = results.filter(test__test_code=filters["test"])
        for r in results.order_by("test__test_code"):
            result_rows.append({
                "code": r.test.test_code, "name": r.test.name,
                "status": r.status, "label": RESULT_AR.get(r.status,
                                                           r.status),
                "checked": r.records_checked,
                "exceptions": r.exceptions_count,
            })
            if r.status in result_totals:
                result_totals[r.status] += 1

    # ------------------------------------- خيارات الفلاتر (من قاعدة حية)
    filter_options = {
        "departments": list(Department.objects.order_by("name").values(
            "id", "name")),
        "accounts": list(Account.objects.order_by("code").values(
            "id", "code", "name")),
        "categories": list(ExpenseCategory.objects.order_by("name").values(
            "id", "name")),
        "periods": [
            {"id": p.id,
             "label": f"{MONTHS_AR[p.month - 1]} {p.fiscal_year.code}"}
            for p in MonthlyPeriod.objects.select_related(
                "fiscal_year").order_by("fiscal_year__year", "month")
        ],
        "risks": list(RISK_LEVELS),
        "tests": list(AuditTest.objects.order_by("test_code").values(
            "test_code", "name")),
    }

    charts = {
        "monthly": {
            "labels": trend_labels,
            "budget": [float(x) for x in trend_budget],
            "actual": [float(x) for x in trend_actual],
        },
        "departments": {
            "labels": [r["name"] for r in dept_rows],
            "budget": [float(r["budget"]) for r in dept_rows],
            "actual": [float(r["actual"]) for r in dept_rows],
        },
        "accounts": {
            "labels": [r["name"] for r in reversed(top_accounts)],
            "total": [float(r["total"]) for r in reversed(top_accounts)],
        },
        "risk": {
            "labels": list(risk_counts.keys()),
            "data": list(risk_counts.values()),
        },
        "test_results": {
            "labels": [RESULT_AR[k] for k in ("pass", "flagged", "fail")],
            "data": [result_totals["pass"], result_totals["flagged"],
                     result_totals["fail"]],
        },
    }

    context = {
        "filters": filters,
        "filter_options": filter_options,
        "kpis": kpis,
        "kpis_fmt": kpis_fmt,
        "window": {"from": date_from, "to": date_to,
                   "months": months, "fiscal_year": fy},
        "dept_rows": dept_rows,
        "top_accounts": top_accounts,
        "oob_rows": oob_rows,
        "risk_counts": risk_counts,
        "status_counts": status_counts,
        "recent_exceptions": recent_exceptions,
        "latest_run": latest_run,
        "latest_run_mode": (MODE_AR.get(latest_run.mode, latest_run.mode)
                            if latest_run else ""),
        "result_rows": result_rows,
        "result_totals": result_totals,
        "charts": charts,
        "now": datetime.now(),
    }
    return render(request, "dashboard/index.html", context)
