"""PHASE 9 — Audit Test Engine (data-driven).

The 14 tests reuse the previous project's approved catalog as REFERENCE
(docs/audit-tests.md + scripts/run_audit_tests.py). Test definitions and ALL
thresholds live in the DB (`audit_tests.parameters`) — nothing here hard-codes
P1–P9 values. Every seeded parameter set carries a Synthetic/Training Rule
declaration. Risk follows the approved 3×3 matrix (RR-01..RR-06) with bands
read from the test's parameters.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count
from django.utils import timezone

from apps.audit_register.models import (
    AuditException,
    AuditRun,
    AuditTest,
    AuditTestResult,
)
from apps.budget.models import BudgetVersion
from apps.expenses.models import Expense
from apps.governance.services import log_action
from apps.procurement.models import Procurement

D = Decimal


# ---------------------------------------------------------------- helpers
def _m(value, decimals: int = 2) -> str:
    if value is None:
        return "—"
    if decimals:
        return f"${float(value):,.{decimals}f}"
    return f"${float(value):,.0f}"


def _bands(params: dict) -> tuple[float, float]:
    b = params.get("risk_bands") or {}
    return (float(b.get("a3", 10000)), float(b.get("a2", 2000)))


def classify_risk(amount, severity: str, params: dict) -> tuple[str, str]:
    """Approved 3×3 matrix — bands read from DB parameters (synthetic)."""
    a3, a2 = _bands(params)
    amt = float(amount or 0)
    if amt >= a3:
        return "High", "RR-01"
    if amt >= a2:
        if severity == "S3":
            return "High", "RR-02"
        return "Medium", "RR-04"
    if severity == "S3":
        return "Medium", "RR-03"
    if severity == "S2":
        return "Low", "RR-05"
    return "Low", "RR-06"


def _exp_base_qs(params: dict):
    qs = Expense.objects.select_related(
        "department", "account", "supplier", "period",
        "expense_category")
    currency = params.get("currency")
    if currency:
        qs = qs.filter(currency=currency)
    return qs


def _proc_qs():
    return Procurement.objects.select_related(
        "department", "account", "supplier")


def _finding(**kw) -> dict:
    base = dict(source_type="", source_id="", source_ref={},
                exception_type="", description="", amount=None,
                currency="", severity="S2")
    base.update(kw)
    return base


# ================================================================ evaluators
# Each evaluator: (test, params) -> (records_checked, [findings, ...])
# Thresholds come ONLY from params (DB-managed).

def eval_budget_overrun_early(test, params):
    """T-BUD-01 — Annual Overrun / Early Consumption."""
    tol = float(params.get("overrun_tolerance", 500))
    cutoff = int(params.get("early_cutoff_month", 10))
    currency = params.get("currency", "YER")

    lines = []
    for version in BudgetVersion.objects.filter(status="approved"):
        lines.extend(version.lines.select_related("department", "account"))
    budget_annual: dict[tuple, Decimal] = {}
    budget_month: dict[tuple, dict] = {}
    labels: dict[tuple, str] = {}
    for line in lines:
        key = (line.department_id, line.account_id)
        months = {m: D(getattr(line, f"m{m:02d}")) or D("0")
                  for m in range(1, 13)}
        budget_month[key] = months
        budget_annual[key] = budget_annual.get(key, D("0")) + sum(
            months.values())
        labels[key] = (f"{line.department.name} / {line.account.name}")

    actual: dict[tuple, Decimal] = {}
    monthly: dict[tuple, dict[int, Decimal]] = {}
    for row in Expense.objects.filter(currency=currency).values(
            "department_id", "account_id", "amount", "expense_date"):
        key = (row["department_id"], row["account_id"])
        actual[key] = actual.get(key, D("0")) + row["amount"]
        m = row["expense_date"].month
        bucket = monthly.setdefault(key, {})
        bucket[m] = bucket.get(m, D("0")) + row["amount"]

    findings = []
    checked = 0
    for key, annual in budget_annual.items():
        checked += 1
        act = actual.get(key, D("0"))
        over = act > annual and (act - annual) > D(str(tol))
        # early consumption: cumulative through cutoff month ≥ annual
        cum = D("0")
        first_100 = None
        for m in range(1, min(cutoff, 12) + 1):
            cum += monthly.get(key, {}).get(m, D("0"))
            if first_100 is None and annual > 0 and cum >= annual:
                first_100 = m
        early = (not over) and annual > 0 and cum >= annual
        if over:
            pct = (float(act) / float(annual) - 1) * 100
            extra = (f" — وصلت 100% من الموازنة بحلول الشهر {first_100:02d}"
                     if first_100 else "")
            findings.append(_finding(
                source_type="budget_combination",
                source_id=f"{key[0]}|{key[1]}",
                source_ref={"department_id": key[0], "account_id": key[1]},
                exception_type="Annual Overrun",
                description=(
                    f"{labels[key]}: تنفيذ سنوي {_m(act, 0)} مقابل الموازنة "
                    f"الفعّالة {_m(annual, 0)} (تجاوز {pct:.1f}%){extra} — "
                    f"عتبة التسامح {_m(tol, 0)} قاعدة تدريبية."),
                amount=act - annual, severity="S2"))
        elif early:
            findings.append(_finding(
                source_type="budget_combination",
                source_id=f"{key[0]}|{key[1]}",
                source_ref={"department_id": key[0], "account_id": key[1]},
                exception_type="Early Consumption",
                description=(
                    f"{labels[key]}: استهلاك تراكمي حتى الشهر "
                    f"{cutoff:02d} {_m(cum, 0)} بلغ 100% من الموازنة "
                    f"السنوية {_m(annual, 0)} مبكرًا — قاعدة تدريبية."),
                amount=cum - annual, severity="S1"))
    return checked, findings


def eval_budget_coverage(test, params):
    """T-BUD-02 — Out-of-Budget Expenditure (left join vs approved lines)."""
    currency = params.get("currency", "YER")
    budget_keys = set()
    for version in BudgetVersion.objects.filter(status="approved"):
        for line in version.lines.values_list("department_id", "account_id"):
            budget_keys.add(line)
    findings = []
    qs = _exp_base_qs(params).filter(currency=currency)
    for e in qs:
        key = (e.department_id, e.account_id)
        if key in budget_keys:
            continue
        findings.append(_finding(
            source_type="expense", source_id=str(e.pk),
            source_ref={"expense_number": e.expense_number,
                        "department_id": e.department_id,
                        "account_id": e.account_id},
            exception_type="Out of Budget",
            description=(
                f"{e.expense_number} — {e.department.name} / "
                f"{e.account.name} بتاريخ {e.expense_date}: لا توجد أي "
                f"موازنة للتركيبة — المبلغ {_m(e.amount)}"),
            amount=e.amount, currency=e.currency, severity="S3"))
    return qs.count(), findings


def eval_monthly_variance(test, params):
    """T-BUD-03 — Unusual Monthly Variance (P6 logic)."""
    mult = Decimal(str(params.get("utilization_multiple", 2.5)))
    excess_min = Decimal(str(params.get("excess_min", 1500)))
    currency = params.get("currency", "YER")

    budget: dict[tuple, Decimal] = {}
    labels: dict[tuple, str] = {}
    for version in BudgetVersion.objects.filter(status="approved"):
        for line in version.lines.select_related("department", "account"):
            for m in range(1, 13):
                key = (line.department_id, line.account_id, m)
                budget[key] = D(getattr(line, f"m{m:02d}") or "0")
                labels[key] = (f"{line.department.name} / "
                               f"{line.account.name}")

    actual: dict[tuple, Decimal] = {}
    for row in Expense.objects.filter(currency=currency).values(
            "department_id", "account_id", "amount", "expense_date"):
        key = (row["department_id"], row["account_id"],
               row["expense_date"].month)
        actual[key] = actual.get(key, D("0")) + row["amount"]

    findings = []
    checked = 0
    for key, bud in budget.items():
        if key not in actual:
            continue
        checked += 1
        if bud <= 0:
            continue
        act = actual[key]
        if act > mult * bud and (act - bud) > excess_min:
            pct = float(act) / float(bud) * 100
            findings.append(_finding(
                source_type="budget_combination",
                source_id=f"{key[0]}|{key[1]}|{key[2]:02d}",
                source_ref={"department_id": key[0],
                            "account_id": key[1], "month": key[2]},
                exception_type="Unusual Monthly Variance",
                description=(
                    f"{labels[key]} — الشهر {key[2]:02d}: تنفيذ شهري "
                    f"{_m(act, 0)} مقابل موازنة {_m(bud, 0)} ({pct:.0f}%) — "
                    f"عتبتان تدريبيتان: {float(mult)}× و {_m(excess_min, 0)}."),
                amount=act - bud, severity="S1"))
    return checked, findings


def eval_proc_min_quotes(test, params):
    """T-PROC-01 — Insufficient Quotations (P1 logic)."""
    min_quotes = int(params.get("min_quotes", 3))
    min_amount = D(str(params.get("min_amount", 1000)))
    qs = _proc_qs().exclude(status="cancelled").annotate(
        n_quotes=Count("quotations"))
    checked = 0
    findings = []
    for p in qs:
        checked += 1
        if p.n_quotes < min_quotes and p.amount >= min_amount:
            findings.append(_finding(
                source_type="procurement", source_id=str(p.pk),
                source_ref={"reference_number": p.reference_number,
                            "department_id": p.department_id},
                exception_type="Insufficient Quotations",
                description=(
                    f"{p.reference_number} — {p.description[:60]}: "
                    f"{_m(p.amount)} بعدد عروض {p.n_quotes} "
                    f"(عتبة تدريبية: {min_quotes} عروض ≥ {_m(min_amount, 0)})"),
                amount=p.amount, severity="S2"))
    return checked, findings


def eval_proc_documents(test, params):
    """T-PROC-02 — Missing PO (Receiving check optional — field N/A now)."""
    po_min = D(str(params.get("po_min_amount", 500)))
    check_receiving = bool(params.get("check_receiving", False))
    checked = 0
    findings = []
    for p in _proc_qs().exclude(status="cancelled"):
        checked += 1
        if not p.purchase_order and p.amount >= po_min:
            findings.append(_finding(
                source_type="procurement", source_id=str(p.pk),
                source_ref={"reference_number": p.reference_number},
                exception_type="Missing PO",
                description=(
                    f"{p.reference_number} — {p.description[:60]}: "
                    f"{_m(p.amount)} بلا أمر شراء (عتبة تدريبية: ≥ "
                    f"{_m(po_min, 0)})"),
                amount=p.amount, severity="S2"))
        if check_receiving:  # declared: field not in current schema
            findings.append(_finding(
                source_type="procurement", source_id=str(p.pk),
                exception_type="Missing Receiving Evidence",
                description=(
                    f"{p.reference_number}: فحص إثبات الاستلام مفعّل لكن "
                    f"حقل الاستلام غير متاح في المخطط الحالي."),
                amount=p.amount, severity="S2"))
    return checked, findings


def eval_proc_approval_pending(test, params):
    """T-PROC-03 — Incomplete Approval (rejected/cancelled = control worked)."""
    pending = list(params.get("pending_statuses", ["draft", "pending"]))
    checked = 0
    findings = []
    for p in _proc_qs():
        checked += 1
        if p.status in pending:
            findings.append(_finding(
                source_type="procurement", source_id=str(p.pk),
                source_ref={"reference_number": p.reference_number,
                            "status": p.status},
                exception_type="Incomplete Approval",
                description=(
                    f"{p.reference_number} — {p.description[:60]}: "
                    f"{_m(p.amount)} ما زالت بحالة «{p.get_status_display()}» "
                    f"— إجراء غير مكتمل."),
                amount=p.amount, severity="S2"))
    return checked, findings


def eval_proc_inactive_supplier(test, params):
    """T-PROC-04 — Inactive Supplier (current supplier state join)."""
    checked = 0
    findings = []
    for p in _proc_qs():
        checked += 1
        if not p.supplier.is_active:
            findings.append(_finding(
                source_type="procurement", source_id=str(p.pk),
                source_ref={"reference_number": p.reference_number,
                            "supplier_id": p.supplier_id},
                exception_type="Inactive Supplier",
                description=(
                    f"{p.reference_number} — المورد {p.supplier.name} "
                    f"حالته معطّل في دليل الموردين — {_m(p.amount)} "
                    f"— يحتاج تأكيد توقيت التعامل."),
                amount=p.amount, severity="S2"))
    return checked, findings


def eval_proc_high_value_low_comp(test, params):
    """T-PROC-05 — High-Value Low-Competition (P9 logic)."""
    high_value = D(str(params.get("high_value", 10000)))
    min_quotes = int(params.get("min_quotes", 3))
    checked = 0
    findings = []
    qs = _proc_qs().exclude(status="cancelled").annotate(
        n_quotes=Count("quotations"))
    for p in qs:
        checked += 1
        if p.amount >= high_value and p.n_quotes < min_quotes:
            findings.append(_finding(
                source_type="procurement", source_id=str(p.pk),
                source_ref={"reference_number": p.reference_number},
                exception_type="High-Value Low Competition",
                description=(
                    f"{p.reference_number} — {p.description[:60]}: "
                    f"{_m(p.amount)} بعدد عروض {p.n_quotes} "
                    f"(نمط تدريبي: ≥ {_m(high_value, 0)} مع < {min_quotes} عروض)"),
                amount=p.amount, severity="S2"))
    return checked, findings


def eval_exp_supporting_docs(test, params):
    """T-EXP-01 — Missing Supporting Document (attachment-based).

    `Doc_Status` Partial is NOT representable in the current schema —
    declared via parameter (`check_partial` defaults to false).
    """
    checked = 0
    findings = []
    for e in _exp_base_qs(params):
        checked += 1
        if not e.attachment:
            findings.append(_finding(
                source_type="expense", source_id=str(e.pk),
                source_ref={"expense_number": e.expense_number,
                            "department_id": e.department_id},
                exception_type="Missing Supporting Document",
                description=(
                    f"{e.expense_number} — {e.department.name} بتاريخ "
                    f"{e.expense_date}: {_m(e.amount)} — بلا مرفق مساند "
                    f"(Doc_Status مشتق من وجود المرفق في المخطط الحالي)"),
                amount=e.amount, currency=e.currency, severity="S2"))
    return checked, findings


def eval_exp_payment_controls(test, params):
    """T-EXP-02 — Unapproved Payment (A) + Large Cash Payment (B) (P4)."""
    large_cash = D(str(params.get("large_cash", 5000)))
    checked = 0
    findings = []
    for e in _exp_base_qs(params):
        checked += 1
        if not e.is_approved:
            findings.append(_finding(
                source_type="expense", source_id=str(e.pk),
                source_ref={"expense_number": e.expense_number},
                exception_type="Unapproved Payment",
                description=(
                    f"{e.expense_number} — {e.description[:60]}: "
                    f"{_m(e.amount)} بحالة غير معتمد "
                    f"(لا اعتماد ولا مرجع قرار) — تنفيذ قبل استكمال الضابط."),
                amount=e.amount, currency=e.currency, severity="S3"))
        if e.payment_method == "cash" and e.amount >= large_cash:
            findings.append(_finding(
                source_type="expense", source_id=str(e.pk),
                source_ref={"expense_number": e.expense_number},
                exception_type="Large Cash Payment",
                description=(
                    f"{e.expense_number} — {e.description[:60]}: دفع نقدي "
                    f"{_m(e.amount)} (عتبة تدريبية: ≥ {_m(large_cash, 0)})"),
                amount=e.amount, currency=e.currency, severity="S3"))
    return checked, findings


def eval_exp_duplicates(test, params):
    """T-EXP-03 — Possible Duplicate Transaction (P8 logic)."""
    dup_days = int(params.get("dup_days", 3))
    dup_min = D(str(params.get("dup_min_amount", 100)))
    currency = params.get("currency", "YER")

    rows = list(
        _exp_base_qs(params).filter(currency=currency).order_by(
            "expense_date", "pk"))
    pairs: dict[tuple, tuple] = {}

    def register_pair(a, b):
        key = tuple(sorted((a.pk, b.pk)))
        if key in pairs:
            return
        orig, dup = (a, b) if a.expense_date <= b.expense_date else (b, a)
        pairs[key] = (orig, dup)

    # (a) same supplier + same amount within N days (amount ≥ floor)
    by_key: dict[tuple, list] = {}
    for e in rows:
        if e.supplier_id and e.amount >= dup_min:
            by_key.setdefault(
                (e.supplier_id, f"{e.amount:.2f}"), []).append(e)
    for group in by_key.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: (x.expense_date, x.pk))
        for a, b in zip(group, group[1:]):
            gap = (b.expense_date - a.expense_date).days
            if 0 < gap <= dup_days:
                register_pair(a, b)

    # (b) same invoice number (shared invoice across rows)
    by_inv: dict[str, list] = {}
    for e in rows:
        if e.invoice_reference:
            by_inv.setdefault(e.invoice_reference, []).append(e)
    for group in by_inv.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: (x.expense_date, x.pk))
        for a, b in zip(group, group[1:]):
            register_pair(a, b)

    findings = []
    for orig, dup in pairs.values():
        gap = (dup.expense_date - orig.expense_date).days
        same_inv = (orig.invoice_reference == dup.invoice_reference
                    and bool(orig.invoice_reference))
        if same_inv:
            basis = f"بنفس رقم الفاتورة {orig.invoice_reference}"
        else:
            basis = (f"بنفس المورد والمبلغ خلال {gap} أيام "
                     f"(حد تدريبي: ≤ {dup_days})")
        findings.append(_finding(
            source_type="expense", source_id=str(dup.pk),
            source_ref={"expense_number": dup.expense_number,
                        "original_id": orig.pk,
                        "original_number": orig.expense_number},
            exception_type="Possible Duplicate Payment",
            description=(
                f"{_m(dup.amount)} — {dup.description[:60]}: تطابق مع "
                f"العملية الأصلية {orig.expense_number} "
                f"({orig.expense_date}) {basis}"),
            amount=dup.amount, currency=dup.currency, severity="S3"))
    return len(rows), findings


def eval_exp_unusual_amount(test, params):
    """T-EXP-04 — Unusual Amount vs peer median (P5 logic).

    Current schema has no expense-level PO field: all expenses are treated
    as no-PO (declared in the seeded rule text).
    """
    mult = Decimal(str(params.get("multiple", 4)))
    floor = D(str(params.get("floor_amount", 500)))

    rows = list(_exp_base_qs(params))
    groups: dict[tuple, list] = {}
    for e in rows:
        groups.setdefault((e.department_id, e.account_id), []).append(e)

    findings = []
    checked = 0
    for group in groups.values():
        amounts = sorted(x.amount for x in group)
        n = len(amounts)
        mid = n // 2
        median = (amounts[mid] if n % 2 else
                  (amounts[mid - 1] + amounts[mid]) / 2)
        if median <= 0:
            continue
        for e in group:
            checked += 1
            if e.amount >= floor and e.amount >= mult * median:
                ratio = float(e.amount) / float(median)
                findings.append(_finding(
                    source_type="expense", source_id=str(e.pk),
                    source_ref={"expense_number": e.expense_number,
                                "department_id": e.department_id,
                                "account_id": e.account_id},
                    exception_type="Unusual Amount",
                    description=(
                        f"{e.expense_number} — {e.description[:60]}: "
                        f"{_m(e.amount)} مقابل وسيط النظائر "
                        f"{_m(median)} ({ratio:.1f}×) — عتبات تدريبية: "
                        f"≥ {float(mult)}× و ≥ {_m(floor, 0)}"),
                    amount=e.amount, currency=e.currency, severity="S2"))
    return checked, findings


def eval_exp_classification(test, params):
    """T-EXP-05 — Suspicious Classification (keyword map is DB-managed)."""
    keyword_map: dict = params.get("keyword_map") or {}
    exclude = set(params.get("exclude_category_codes") or [])
    # normalize maps
    norm_map = {}
    for code, kws in keyword_map.items():
        norm_map[str(code).lower()] = [str(k).lower() for k in kws]

    checked = 0
    findings = []
    for e in _exp_base_qs(params):
        checked += 1
        cat = e.expense_category or e.account.expense_category
        cat_code = (cat.code if cat else "") or ""
        if cat_code.lower() in {x.lower() for x in exclude}:
            continue  # excluded by design (e.g., payroll-style descriptions)
        desc = (e.description or "").lower()
        mapped = None
        for code, kws in norm_map.items():
            if any(k in desc for k in kws):
                mapped = code
                break
        if mapped and mapped != cat_code.lower():
            findings.append(_finding(
                source_type="expense", source_id=str(e.pk),
                source_ref={"expense_number": e.expense_number,
                            "category_code": cat_code,
                            "mapped_category": mapped.upper()},
                exception_type="Suspicious Classification",
                description=(
                    f"الوصف «{e.description[:80]}» يشير إلى فئة "
                    f"{mapped.upper()} لكنها مصنّفة ضمن {cat_code} — "
                    f"{_m(e.amount)} — خريطة كلمات تدريبية (DB-managed)."),
                amount=e.amount, currency=e.currency, severity="S2"))
    return checked, findings


def eval_exp_purchase_no_po(test, params):
    """T-EXP-06 — Purchase-type expenditure without PO (P2 logic).

    No expense-level PO field in the current schema → all expenses treated
    as no-PO (declared in the seeded rule text + parameter).
    """
    keywords = [str(k).lower()
                for k in (params.get("purchase_keywords") or [])]
    po_min = D(str(params.get("po_min_amount", 1000)))
    checked = 0
    findings = []
    for e in _exp_base_qs(params):
        checked += 1
        desc = (e.description or "").lower()
        if not desc.startswith("payment for") and any(
                k in desc for k in keywords) and e.amount >= po_min:
            findings.append(_finding(
                source_type="expense", source_id=str(e.pk),
                source_ref={"expense_number": e.expense_number,
                            "department_id": e.department_id},
                exception_type="Purchase without PO",
                description=(
                    f"{e.expense_number} — {e.description[:60]}: "
                    f"{_m(e.amount)} بوصف شرائي بلا أمر شراء "
                    f"(عتبة تدريبية: ≥ {_m(po_min, 0)})"),
                amount=e.amount, currency=e.currency, severity="S2"))
    return checked, findings


# ---------------------------------------------------------------- registry
EVALUATORS = {
    "budget_overrun_early": eval_budget_overrun_early,
    "budget_coverage": eval_budget_coverage,
    "monthly_variance": eval_monthly_variance,
    "proc_min_quotes": eval_proc_min_quotes,
    "proc_documents": eval_proc_documents,
    "proc_approval_pending": eval_proc_approval_pending,
    "proc_inactive_supplier": eval_proc_inactive_supplier,
    "proc_high_value_low_comp": eval_proc_high_value_low_comp,
    "exp_supporting_docs": eval_exp_supporting_docs,
    "exp_payment_controls": eval_exp_payment_controls,
    "exp_duplicates": eval_exp_duplicates,
    "exp_unusual_amount": eval_exp_unusual_amount,
    "exp_classification": eval_exp_classification,
    "exp_purchase_no_po": eval_exp_purchase_no_po,
}

ENGINE_CHOICES = [
    (key, key) for key in sorted(EVALUATORS)
]


def next_run_number() -> str:
    year = timezone.now().year
    prefix = f"AR-{year}-"
    last = (AuditRun.objects.filter(run_number__startswith=prefix)
            .order_by("-run_number").values_list("run_number", flat=True)
            .first())
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:05d}"


def next_finding_code() -> str:
    from apps.audit_register.models import AuditFinding
    year = timezone.now().year
    prefix = f"F-{year}-"
    last = (AuditFinding.objects.filter(finding_code__startswith=prefix)
            .order_by("-finding_code").values_list("finding_code",
                                                   flat=True).first())
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:05d}"


# ---------------------------------------------------------------- run engine
def start_run(tests, user, *, mode: str, request=None) -> AuditRun:
    """Execute tests → store run + results + exceptions (traceable)."""
    tests = list(tests)
    run = AuditRun.objects.create(
        run_number=next_run_number(), mode=mode,
        status=AuditRun.STATUS_RUNNING, triggered_by=user)
    log_action(
        action="entity_created", entity_type="audit_run", entity_id=run.pk,
        diff={"run_number": run.run_number, "mode": mode,
              "tests": [t.test_code for t in tests]},
        request=request, actor=user)

    totals = {"pass": 0, "flagged": 0, "fail": 0, "exceptions": 0}
    for test in tests:
        params = dict(test.parameters or {})
        try:
            evaluator = EVALUATORS.get(test.engine_key)
            if evaluator is None:
                raise ValueError(
                    f"لا يوجد منفّذ مسجّل لمفتاح المحرّك «{test.engine_key}».")
            checked, findings = evaluator(test, params)
            status = (AuditTestResult.STATUS_FLAGGED if findings
                      else AuditTestResult.STATUS_PASS)
            if findings:
                explanation = (
                    f"أُعلِّم {len(findings)} استثناء من أصل {checked} "
                    f"سجلًا — كل استثناء أدناه يشرح قيمه الفعلية مقابل "
                    f"عتبات الاختبار.")
            else:
                explanation = (
                    f"نجح — لا استثناءات: فُحص {checked} سجلًا وفق قاعدة "
                    f"الاختبار ومعاملاتها المخزّنة في قاعدة البيانات.")
            result = AuditTestResult.objects.create(
                run=run, test=test, status=status,
                records_checked=checked, exceptions_count=len(findings),
                explanation=explanation, params_snapshot=params)
            for f in findings:
                risk, ref = classify_risk(f.get("amount"), f["severity"],
                                          params)
                AuditException.objects.create(
                    run=run, result=result, test=test,
                    test_code=test.test_code,
                    source_type=f["source_type"],
                    source_id=str(f["source_id"]),
                    source_ref=f.get("source_ref") or {},
                    exception_type=f["exception_type"],
                    title=f["exception_type"],
                    explanation=f["description"],
                    amount=(D(str(f["amount"]))
                            if f.get("amount") is not None else None),
                    currency=f.get("currency") or "",
                    control_severity=f["severity"],
                    risk_level=risk, risk_rule_ref=ref,
                    auditor_action=test.auditor_action)
            totals["exceptions"] += len(findings)
            totals[status] += 1
        except Exception as exc:  # noqa: BLE001 — engine errors become `fail`
            AuditTestResult.objects.create(
                run=run, test=test, status=AuditTestResult.STATUS_FAIL,
                records_checked=0, exceptions_count=0,
                explanation=(
                    f"فشل التنفيذ — لن يُعتمد نجاح الاختبار حتى يُعالج "
                    f"السبب: {exc}"),
                params_snapshot=params, error=str(exc)[:1000])
            totals["fail"] += 1

    run.tests_total = len(tests)
    run.tests_pass = totals["pass"]
    run.tests_flagged = totals["flagged"]
    run.tests_fail = totals["fail"]
    run.exceptions_total = totals["exceptions"]
    run.status = AuditRun.STATUS_FAILED if (
        totals["fail"] and totals["fail"] == len(tests)) else (
        AuditRun.STATUS_COMPLETED)
    run.finished_at = timezone.now()
    run.save()
    log_action(
        action="entity_updated", entity_type="audit_run", entity_id=run.pk,
        diff={"stage": "finished", "pass": totals["pass"],
              "flagged": totals["flagged"], "fail": totals["fail"],
              "exceptions": totals["exceptions"]},
        request=request, actor=user)
    return run


def resolve_tests(*, mode: str, test_ids=None):
    """Map UI intent → queryset (all_active honors Active/Inactive)."""
    if mode == AuditRun.MODE_ALL:
        return AuditTest.objects.filter(is_active=True), []
    ids = [int(i) for i in (test_ids or [])]
    qs = AuditTest.objects.filter(pk__in=ids).order_by("test_code")
    if mode == AuditRun.MODE_SINGLE and len(ids) != 1:
        raise ValueError("تشغيل اختبار واحد يتطلب معرّفًا واحدًا.")
    if not ids:
        raise ValueError("لم يتم تحديد أي اختبار للتشغيل.")
    return qs, ids
