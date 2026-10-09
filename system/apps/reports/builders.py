"""PHASE 12 — بناء التقارير التسعة من استعلامات PostgreSQL حية.

كل تقرير: (أ) أعمدة (ب) صفوف حيّة (ج) ملخّص — ثم يُعرض HTML مع Print CSS
ويُصدَّر CSV/XLSX من نفس البنية بالضبط. لا أرقام ثابتة في أي مكان.
"""
from collections import OrderedDict
from decimal import Decimal

from django.db.models import Count, Exists, Max, OuterRef, Q, Subquery, Sum

from apps.audit_register.models import (
    AuditException,
    AuditFinding,
    AuditRun,
    AuditTestResult,
)
from apps.budget.models import BudgetLine, BudgetVersion
from apps.expenses.models import Expense

D = Decimal

MONTHS_AR = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]
RISK_AR = {"High": "High", "Medium": "Medium", "Low": "Low"}
RESULT_AR = {"pass": "ناجح", "flagged": "مُعلَّم", "fail": "فاشل"}
STATUS_AR = {"open": "مفتوح", "acknowledged": "مُعتمد", "resolved": "مُعالج"}
FINDING_STATUS_AR = {"open": "مفتوح", "in_progress": "قيد المعالجة",
                     "closed": "مُغلق"}
SOURCE_TYPE_AR = {"expense": "مصروف", "procurement": "مشتريات",
                  "budget_combination": "تركيبة موازنة"}


# ------------------------------------------------------------------ cells
def text_c(value, url=None):
    cell = {"d": "" if value is None else str(value),
            "v": "" if value is None else str(value)}
    if url:
        cell["url"] = url
    return cell


def money_c(value: Decimal):
    value = value or D("0")
    return {"d": f"{value:,.2f}", "v": value}


def int_c(value: int):
    return {"d": str(int(value)), "v": int(value)}


def pct_c(value):
    if value is None:
        return {"d": "—", "v": ""}
    return {"d": f"{float(value):.1f}", "v": round(float(value), 2)}


def date_c(value):
    if not value:
        return {"d": "—", "v": ""}
    return {"d": str(value), "v": str(value)}


def col(key, label):
    return {"key": key, "label": label}


# ---------------------------------------------------------------- filters
def parse_filters(request) -> dict:
    def int_or_none(raw):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    risk = request.GET.get("risk", "")
    if risk not in ("High", "Medium", "Low"):
        risk = ""
    return {
        "period": int_or_none(request.GET.get("period")),
        "department": int_or_none(request.GET.get("department")),
        "account": int_or_none(request.GET.get("account")),
        "category": int_or_none(request.GET.get("category")),
        "risk": risk,
        "test": request.GET.get("test", "").strip(),
    }


def resolve_window(filters: dict):
    from apps.reference.models import FiscalYear

    fy = FiscalYear.objects.order_by("-year").first()
    if filters["period"]:
        from apps.reference.models import MonthlyPeriod
        period = MonthlyPeriod.objects.select_related("fiscal_year").filter(
            pk=filters["period"]).first()
        if period:
            return ([period.month], period.start_date, period.end_date,
                    period.fiscal_year)
    if fy:
        return (list(range(1, 13)), fy.start_date, fy.end_date, fy)
    return (list(range(1, 13)), None, None, None)


def filtered_budget_lines(filters, fy):
    latest_approved = BudgetVersion.objects.filter(
        budget_id=OuterRef("version__budget_id"), status=BudgetVersion.STATUS_APPROVED,
    ).order_by("-version").values("pk")[:1]
    qs = BudgetLine.objects.filter(version_id=Subquery(latest_approved))
    analytical_siblings = BudgetLine.objects.filter(
        version_id=OuterRef("version_id"), department_id=OuterRef("department_id"),
        account_id=OuterRef("account_id"), analytical_account__isnull=False,
    )
    qs = qs.alias(has_analytical=Exists(analytical_siblings)).filter(
        Q(analytical_account__isnull=False) | Q(has_analytical=False))
    if fy is not None:
        qs = qs.filter(version__budget__fiscal_year=fy)
    if filters["department"]:
        qs = qs.filter(department_id=filters["department"])
    if filters["account"]:
        qs = qs.filter(account_id=filters["account"])
    if filters["category"]:
        qs = qs.filter(account__expense_category_id=filters["category"])
    return qs.select_related("department", "account")


def filtered_expenses(filters, date_from, date_to):
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


def filtered_exceptions(filters, date_from, date_to):
    """فلاتر الخطر/الاختبار دائمًا؛ الفترة (تاريخ رصد) عند اختيارها."""
    qs = AuditException.objects.all()
    if filters["test"]:
        qs = qs.filter(test_code=filters["test"])
    if filters["risk"]:
        qs = qs.filter(risk_level=filters["risk"])
    if filters["period"] and date_from and date_to:
        qs = qs.filter(detected_at__date__gte=date_from,
                       detected_at__date__lte=date_to)
    return qs


def budget_for(budget_qs, months) -> Decimal:
    cols = {f"m{m:02d}": Sum(f"m{m:02d}") for m in months}
    if not cols:
        return D("0")
    agg = budget_qs.aggregate(**cols)
    return sum((agg[c] or D("0")) for c in cols)


# =================================================================== 1
def build_budget_vs_actual(f, w):
    months, date_from, date_to, fy = w
    lines = filtered_budget_lines(f, fy)
    exps = filtered_expenses(f, date_from, date_to)

    budget: dict[tuple, Decimal] = {}
    labels: dict[tuple, tuple] = OrderedDict()
    cols = {f"m{m:02d}": Sum(f"m{m:02d}") for m in months}
    if cols:
        for row in lines.values("department_id", "department__name",
                                "account_id", "account__name").annotate(**cols):
            key = (row["department_id"], row["account_id"])
            budget[key] = sum((row[c] or D("0")) for c in cols)
            labels[key] = (row["department__name"], row["account__name"])
    actual: dict[tuple, Decimal] = {}
    for row in exps.values("department_id", "account_id",
                           "department__name", "account__name").annotate(
            total=Sum("amount")):
        key = (row["department_id"], row["account_id"])
        actual[key] = row["total"] or D("0")
        labels.setdefault(key, (row["department__name"],
                                row["account__name"]))

    rows, tb, ta = [], D("0"), D("0")
    for key in sorted(labels, key=lambda k: (labels[k][0], labels[k][1])):
        b, a = budget.get(key, D("0")), actual.get(key, D("0"))
        tb += b
        ta += a
        util = (a / b * 100) if b > 0 else None
        rows.append({
            "department": text_c(labels[key][0]),
            "account": text_c(labels[key][1]),
            "budget": money_c(b),
            "actual": money_c(a),
            "variance": money_c(b - a),
            "utilization": pct_c(util),
        })
    columns = [col("department", "الإدارة"), col("account", "الحساب"),
               col("budget", "الموازنة"), col("actual", "التنفيذ"),
               col("variance", "الانحراف"), col("utilization", "الاستخدام %")]
    summary = [
        {"label": "Effective Budget", "value": f"{tb:,.2f}"},
        {"label": "Actual Expenses", "value": f"{ta:,.2f}"},
        {"label": "Variance", "value": f"{tb - ta:,.2f}"},
        {"label": "Utilization %",
         "value": (f"{ta / tb * 100:.1f}" if tb > 0 else "—")},
    ]
    return columns, rows, summary


# =================================================================== 2
def build_variance(f, w):
    months, date_from, date_to, fy = w
    lines = filtered_budget_lines(f, fy)
    exps = filtered_expenses(f, date_from, date_to)

    budget: dict[tuple, Decimal] = {}
    labels: dict[tuple, tuple] = OrderedDict()
    for line in lines:
        for m in months:
            key = (line.department_id, line.account_id, m)
            budget[key] = budget.get(key, D("0")) + D(getattr(line, f"m{m:02d}") or "0")
            labels[key] = (line.department.name, line.account.name, m)
    actual: dict[tuple, Decimal] = {}
    for row in exps.values("department_id", "account_id",
                           "expense_date", "amount", "department__name",
                           "account__name"):
        key = (row["department_id"], row["account_id"],
               row["expense_date"].month)
        actual[key] = actual.get(key, D("0")) + row["amount"]
        labels.setdefault(key, (row["department__name"],
                                row["account__name"],
                                row["expense_date"].month))

    rows, pos, neg = [], D("0"), D("0")
    keys = sorted(set(budget) | set(actual),
                  key=lambda k: (labels.get(k, ("", "", 99))[0],
                                 labels.get(k, ("", "", 99))[1], k[-1]))
    for key in keys:
        b = budget.get(key, D("0"))
        a = actual.get(key, D("0"))
        if b == 0 and a == 0:
            continue
        var = a - b
        if var > 0:
            status, pos = "تجاوز", pos + var
        elif var < 0:
            status, neg = "استهلاك أقل", neg + var
        else:
            status = "مطابق"
        name, acct, m = labels.get(key, ("—", "—", key[-1]))
        rows.append({
            "department": text_c(name),
            "account": text_c(acct),
            "month": text_c(MONTHS_AR[m - 1] if isinstance(m, int) and
                            1 <= m <= 12 else m),
            "budget": money_c(b),
            "actual": money_c(a),
            "variance": money_c(var),
            "status": text_c(status),
        })
    rows.sort(key=lambda r: (-abs(D(r["variance"]["v"] or 0)),
                             r["department"]["d"]))
    columns = [col("department", "الإدارة"), col("account", "الحساب"),
               col("month", "الشهر"), col("budget", "الموازنة"),
               col("actual", "التنفيذ"), col("variance", "الانحراف"),
               col("status", "الحالة")]
    summary = [
        {"label": "عدد السطور", "value": str(len(rows))},
        {"label": "إجمالي تجاوزات (تفاؤل سلبي)", "value": f"{pos:,.2f}"},
        {"label": "إجمالي استهلاك أقل", "value": f"{neg:,.2f}"},
    ]
    return columns, rows, summary


# =================================================================== 3
def build_out_of_budget(f, w):
    months, date_from, date_to, fy = w
    lines = filtered_budget_lines(f, fy)
    keys = set(lines.values_list("department_id", "account_id"))
    exps = filtered_expenses(f, date_from, date_to)

    rows, total = [], D("0")
    for e in exps.select_related("department", "account",
                                 "expense_category"):
        if (e.department_id, e.account_id) in keys:
            continue
        total += e.amount
        rows.append({
            "expense_number": text_c(e.expense_number),
            "date": date_c(e.expense_date),
            "department": text_c(e.department.name),
            "account": text_c(e.account.name),
            "category": text_c(e.expense_category.name
                               if e.expense_category else "—"),
            "description": text_c((e.description or "")[:80]),
            "amount": money_c(e.amount),
        })
    columns = [col("expense_number", "رقم المصروف"), col("date", "التاريخ"),
               col("department", "الإدارة"), col("account", "الحساب"),
               col("category", "التصنيف"), col("description", "البيان"),
               col("amount", "المبلغ")]
    summary = [
        {"label": "عدد المصروفات خارج الموازنة", "value": str(len(rows))},
        {"label": "Out-of-Budget Amount", "value": f"{total:,.2f}"},
    ]
    return columns, rows, summary


# =================================================================== 4
def build_expense_analysis(f, w):
    _, date_from, date_to, _ = w
    exps = filtered_expenses(f, date_from, date_to)
    groups = (exps.values("department__name", "account__name",
                          "expense_category__name")
                  .annotate(total=Sum("amount"), n=Count("id"),
                            avg=Sum("amount") / Count("id"),
                            top=Max("amount"))
                  .order_by("-total"))
    rows, grand, count = [], D("0"), 0
    for g in groups:
        total = g["total"] or D("0")
        grand += total
        count += g["n"]
        rows.append({
            "department": text_c(g["department__name"] or "—"),
            "account": text_c(g["account__name"] or "—"),
            "category": text_c(g["expense_category__name"] or "—"),
            "count": int_c(g["n"]),
            "total": money_c(total),
            "average": money_c(g["avg"] or D("0")),
            "max": money_c(g["top"] or D("0")),
        })
    columns = [col("department", "الإدارة"), col("account", "الحساب"),
               col("category", "التصنيف"), col("count", "عدد المصروفات"),
               col("total", "الإجمالي"), col("average", "المتوسط"),
               col("max", "الأعلى")]
    summary = [
        {"label": "إجمالي المصروفات", "value": f"{grand:,.2f}"},
        {"label": "عدد المصروفات", "value": str(count)},
        {"label": "عدد المجموعات", "value": str(len(rows))},
    ]
    return columns, rows, summary


# =================================================================== 5
def build_procurement_exceptions(f, w):
    _, date_from, date_to, _ = w
    excs = (filtered_exceptions(f, date_from, date_to)
            .filter(source_type="procurement").select_related("run"))
    rows, total = [], D("0")
    for e in excs.order_by("-detected_at"):
        total += e.amount or D("0")
        ref = (e.source_ref or {}).get("reference_number", "")
        rows.append({
            "detected": date_c(e.detected_at.date() if e.detected_at else ""),
            "test_code": text_c(e.test_code),
            "exception_type": text_c(e.exception_type),
            "title": text_c(e.title, url=f"/audit/exceptions/{e.pk}/"),
            "reference": text_c(ref),
            "amount": money_c(e.amount or D("0")),
            "risk": text_c(e.risk_level),
            "status": text_c(STATUS_AR.get(e.status, e.status)),
        })
    columns = [col("detected", "تاريخ الرصد"), col("test_code", "الاختبار"),
               col("exception_type", "النوع"), col("title", "الاستثناء"),
               col("reference", "مرجع المشتريات"), col("amount", "المبلغ"),
               col("risk", "Risk"), col("status", "Status")]
    summary = [
        {"label": "عدد استثناءات المشتريات", "value": str(len(rows))},
        {"label": "إجمالي المبالغ", "value": f"{total:,.2f}"},
        {"label": "High",
         "value": str(sum(1 for r in rows if r["risk"]["d"] == "High"))},
    ]
    return columns, rows, summary


# =================================================================== 6
def build_test_results(f, w):
    _, date_from, date_to, _ = w
    qs = AuditTestResult.objects.select_related("run", "test")
    if f["test"]:
        qs = qs.filter(test__test_code=f["test"])
    if f["period"] and date_from and date_to:
        qs = qs.filter(evaluated_at__date__gte=date_from,
                       evaluated_at__date__lte=date_to)
    rows = []
    totals = {"pass": 0, "flagged": 0, "fail": 0}
    for r in qs.order_by("-run_id", "test__test_code"):
        totals[r.status] = totals.get(r.status, 0) + 1
        rows.append({
            "run": text_c(r.run.run_number,
                          url=f"/audit/runs/{r.run_id}/"),
            "test_code": text_c(r.test.test_code),
            "test_name": text_c(r.test.name),
            "status": text_c(RESULT_AR.get(r.status, r.status)),
            "checked": int_c(r.records_checked),
            "exceptions": int_c(r.exceptions_count),
            "evaluated": date_c(r.evaluated_at),
        })
    columns = [col("run", "الجولة"), col("test_code", "الاختبار"),
               col("test_name", "الاسم"), col("status", "الحالة"),
               col("checked", "سجلات مفحوصة"), col("exceptions", "استثناءات"),
               col("evaluated", "وقت التقييم")]
    summary = [
        {"label": "ناجح", "value": str(totals.get("pass", 0))},
        {"label": "مُعلَّم", "value": str(totals.get("flagged", 0))},
        {"label": "فاشل", "value": str(totals.get("fail", 0))},
        {"label": "إجمالي النتائج", "value": str(len(rows))},
    ]
    return columns, rows, summary


# =================================================================== 7
def build_exception_register(f, w):
    _, date_from, date_to, _ = w
    excs = filtered_exceptions(f, date_from, date_to).select_related("run")
    rows = []
    for e in excs.order_by("-detected_at", "-pk"):
        rows.append({
            "pk": int_c(e.pk),
            "detected": date_c(e.detected_at),
            "test_code": text_c(e.test_code),
            "exception_type": text_c(e.exception_type),
            "title": text_c(e.title, url=f"/audit/exceptions/{e.pk}/"),
            "source": text_c(
                f"{SOURCE_TYPE_AR.get(e.source_type, e.source_type)} "
                f"#{e.source_id}"),
            "amount": money_c(e.amount or D("0")),
            "risk": text_c(e.risk_level),
            "status": text_c(STATUS_AR.get(e.status, e.status)),
            "run": text_c(e.run.run_number),
        })
    # عمود الربط إلى صفحة الاستثناء
    columns = [col("pk", "#"), col("detected", "وقت الرصد"),
               col("test_code", "الاختبار"), col("exception_type", "النوع"),
               col("title", "العنوان"), col("source", "المصدر"),
               col("amount", "المبلغ"), col("risk", "Risk"),
               col("status", "Status"), col("run", "الجولة")]
    risk_counts = {"High": 0, "Medium": 0, "Low": 0}
    for r in rows:
        risk_counts[r["risk"]["d"]] = risk_counts.get(r["risk"]["d"], 0) + 1
    summary = [
        {"label": "إجمالي الاستثناءات", "value": str(len(rows))},
        {"label": "High", "value": str(risk_counts["High"])},
        {"label": "Medium", "value": str(risk_counts["Medium"])},
        {"label": "Low", "value": str(risk_counts["Low"])},
    ]
    return columns, rows, summary


# =================================================================== 8
def build_risk_report(f, w):
    _, date_from, date_to, _ = w
    excs = filtered_exceptions(f, date_from, date_to)
    findings = AuditFinding.objects.all()
    if f["risk"]:
        findings = findings.filter(risk_level=f["risk"])
    if f["period"] and date_from and date_to:
        findings = findings.filter(created_at__date__gte=date_from,
                                   created_at__date__lte=date_to)

    exc_by_risk = {r["risk_level"]: r for r in
                   excs.values("risk_level").annotate(
                       n=Count("id"), total=Sum("amount"))}
    fnd_by_risk = {r["risk_level"]: r["n"] for r in
                   findings.values("risk_level").annotate(n=Count("id"))}
    levels = ["High", "Medium", "Low"] if not f["risk"] else [f["risk"]]
    rows = []
    for lvl in levels:
        er = exc_by_risk.get(lvl, {})
        rows.append({
            "risk": text_c(lvl),
            "exceptions": int_c(er.get("n", 0)),
            "amount": money_c(er.get("total") or D("0")),
            "findings": int_c(fnd_by_risk.get(lvl, 0)),
        })
    columns = [col("risk", "Risk Level"), col("exceptions", "الاستثناءات"),
               col("amount", "إجمالي مبالغ الاستثناءات"),
               col("findings", "النتائج (Findings)")]
    summary = [
        {"label": "إجمالي الاستثناءات",
         "value": str(sum(r["exceptions"]["v"] for r in rows))},
        {"label": "إجمالي النتائج",
         "value": str(sum(r["findings"]["v"] for r in rows))},
        {"label": "منطق التقييم",
         "value": "مصفوفة 3×3 تفسيرية — لا AI/ML"},
    ]
    return columns, rows, summary


# =================================================================== 9
def build_findings(f, w):
    _, date_from, date_to, _ = w
    qs = AuditFinding.objects.all()
    if f["risk"]:
        qs = qs.filter(risk_level=f["risk"])
    if f["period"] and date_from and date_to:
        qs = qs.filter(created_at__date__gte=date_from,
                       created_at__date__lte=date_to)
    rows = []
    for fd in qs.order_by("-created_at"):
        rows.append({
            "finding_code": text_c(fd.finding_code,
                                   url=f"/audit/findings/{fd.pk}/"),
            "title": text_c(fd.title),
            "risk": text_c(fd.risk_level),
            "status": text_c(FINDING_STATUS_AR.get(fd.status, fd.status)),
            "recommendation": text_c(fd.recommendation),
            "management_action": text_c(fd.management_action or "—"),
            "linked": int_c(fd.exceptions.count()),
        })
    columns = [col("finding_code", "الرقم"), col("title", "Finding"),
               col("risk", "Risk"), col("status", "Status"),
               col("recommendation", "Recommendation"),
               col("management_action", "Management Action"),
               col("linked", "استثناءات مرتبطة")]
    summary = [
        {"label": "عدد النتائج", "value": str(len(rows))},
        {"label": "مفتوحة",
         "value": str(sum(1 for r in rows if r["status"]["d"] == "مفتوح"))},
        {"label": "High",
         "value": str(sum(1 for r in rows if r["risk"]["d"] == "High"))},
    ]
    return columns, rows, summary


# ================================================================= registry
REPORTS = {
    "budget-vs-actual": {
        "title": "Budget vs Actual",
        "title_ar": "الموازنة مقابل التنفيذ",
        "description": "كل إدارة × حساب: الموازنة الفعّالة والتنفيذ والانحراف والاستخدام.",
        "filters": ("period", "department", "account", "category"),
        "builder": build_budget_vs_actual,
    },
    "variance": {
        "title": "Variance Report",
        "title_ar": "تقرير الانحرافات",
        "description": "انحراف شهري (إدارة × حساب × شهر) مرتّب بالانحراف المطلق.",
        "filters": ("period", "department", "account", "category"),
        "builder": build_variance,
    },
    "out-of-budget": {
        "title": "Out-of-Budget Report",
        "title_ar": "المصروفات خارج الموازنة",
        "description": "مصروفات بلا تركيبة (إدارة × حساب) معتمدة.",
        "filters": ("period", "department", "account", "category"),
        "builder": build_out_of_budget,
    },
    "expense-analysis": {
        "title": "Expense Analysis",
        "title_ar": "تحليل المصروفات",
        "description": "تجميع حسب الإدارة والحساب والتصنيف: عدد وإجمالي ومتوسط وأعلى.",
        "filters": ("period", "department", "account", "category"),
        "builder": build_expense_analysis,
    },
    "procurement-exceptions": {
        "title": "Procurement Exceptions",
        "title_ar": "استثناءات المشتريات",
        "description": "استثناءات المحرك التي مصدرها معاملات مشتريات.",
        "filters": ("period", "risk", "test"),
        "builder": build_procurement_exceptions,
    },
    "test-results": {
        "title": "Audit Test Results",
        "title_ar": "نتائج الاختبارات الرقابية",
        "description": "نتائج الجولات: ناجح/مُعلَّم/فاشل لكل اختبار.",
        "filters": ("period", "test"),
        "builder": build_test_results,
    },
    "exception-register": {
        "title": "Exception Register",
        "title_ar": "سجل الاستثناءات",
        "description": "السجل الكامل للاستثناءات مع الخطر والحالة والجولة والربط.",
        "filters": ("period", "risk", "test"),
        "builder": build_exception_register,
    },
    "risk-report": {
        "title": "Risk Report",
        "title_ar": "تقرير المخاطر",
        "description": "توزيع High/Medium/Low على الاستثناءات والنتائج — مصفوفة تفسيرية فقط.",
        "filters": ("period", "risk"),
        "builder": build_risk_report,
    },
    "findings": {
        "title": "Audit Findings & Recommendations",
        "title_ar": "النتائج والتوصيات الرقابية",
        "description": "كل Finding مع التوصية وإجراء الإدارة والخطر والحالة.",
        "filters": ("period", "risk"),
        "builder": build_findings,
    },
}
