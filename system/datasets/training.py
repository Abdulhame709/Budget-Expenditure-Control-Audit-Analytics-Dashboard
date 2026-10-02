"""PHASE 13 — Synthetic Training Dataset + Ground Truth for the Audit Engine.

SYNTHETIC / تدريبية بالكامل
---------------------------
كل سجل في هذا الملف اصطناعي مُنشأ لأغراض التدريب والاختبار الآلي فقط.
* لا يمثل أي شركة أو جهة حقيقية، ولا يوجد أي ارتباط بأي صاحب عمل أو
  جهة حقيقية (لا اسم، لا رقم، لا أثر بيانات حقيقية).
* العتبات والقواعد الرقابية المطبّقة مُصرَّح بها كـ
  «Synthetic / Training Rule Assumptions» داخل قاعدة البيانات (P1–P9).
* المبالغ والتواريخ وال往来 مُختلقة بالكامل (Owner: Abdulhameed).

Ground Truth
------------
المتوقع مُعلن مسبقًا في `EXPECTED_EXCEPTIONS` كمجموعة مفاتيح
(test_code, exception_type, subject):

    expense:{expense_number}          ← استثناء مصدره مصروف
    proc:{reference_number}           ← استثناء مصدره مشتريات
    combo:{dept_code}:{acc_code}      ← تركيبة موازنة (T-BUD-01 / 02)
    combo:{dept_code}:{acc_code}:mMM  ← تركيبة × شهر (T-BUD-03)

الاختبار في `apps/audit_register/tests_dataset.py` يقارن تساويًا تامًا
(للوجهين) بين ما رصدّه المحرك فعليًا وبين هذه المجموعة: أي استثناء
ناقص أو أي علم زائد = فشل الاختبار.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.core.files.base import ContentFile

D = Decimal

SYNTHETIC_DECLARATION = (
    "SYNTHETIC TRAINING DATASET — بيانات تدريبية اصطناعية بالكامل: "
    "لا تمثل أي شركة أو جهة حقيقية ولا مصدرها أي بيانات فعلية."
)

DS_PASSWORD = "Dataset-Training-2026!"
ADMIN_PASSWORD = "Admin-Training-2026!"

# ============================================================ dimensions
FISCAL_YEAR = {
    "code": "FY2026", "name": "السنة المالية 2026 (تدريبية)", "year": 2026,
    "start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31),
}

# month → (first day, last day) — 2026 is not a leap year
_PERIOD_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTHLY_PERIODS = [
    {"month": m, "start_date": date(2026, m, 1),
     "end_date": date(2026, m, _PERIOD_DAYS[m - 1]), "status": "open"}
    for m in range(1, 13)
]

DEPARTMENTS = [
    {"code": "D-LOG", "name": "اللوجستيات"},
    {"code": "D-IT", "name": "تكنولوجيا المعلومات"},
    {"code": "D-MKT", "name": "التسويق"},
    {"code": "D-QA", "name": "الجودة والاعتماد"},
]

CATEGORIES = [
    {"code": "SUPPLIES", "name": "مستلزمات"},
    {"code": "TRAVEL", "name": "سفر وتنقلات"},
    {"code": "SERVICES", "name": "خدمات"},
    {"code": "PAYROLL", "name": "رواتب وأجور"},
]

ACCOUNTS = [
    {"code": "5601", "name": "مستلزمات عامة", "cat": "SUPPLIES"},
    {"code": "5602", "name": "سفر وتنقلات", "cat": "TRAVEL"},
    {"code": "5603", "name": "خدمات استشارية", "cat": "SERVICES"},
    {"code": "5604", "name": "مستلزمات تشغيلية", "cat": "SUPPLIES"},
    {"code": "5605", "name": "رواتب وأجور", "cat": "PAYROLL"},
]

SUPPLIERS = [
    {"code": "SUP-TRN-A", "name": "مؤسسة التدريب المتقدمة", "is_active": True},
    {"code": "SUP-TRN-B", "name": "شركة الأجهزة المكتبية", "is_active": True},
    {"code": "SUP-TRN-C", "name": "دار النشر المتخصصة", "is_active": False},
    {"code": "SUP-TRN-D", "name": "وكالة التنقلات", "is_active": True},
]

USERS = [
    {"username": "ds_admin", "role": "admin"},
    {"username": "ds_auditor", "role": "auditor"},
    {"username": "ds_finance", "role": "finance"},
    {"username": "ds_mgmt", "role": "management"},
]

# ============================================================ budget
BUDGET_NAME = "ميزانية التدريب المتقدمة (تدريبية)"
# (dept_code, account_code, monthly amount) — uniform across the 12 months
BUDGET_LINES = [
    ("D-LOG", "5604", D("2000")),   # annual 24000 — INTENDED T-BUD-01 over
    ("D-LOG", "5601", D("1000")),   # annual 12000 — Feb variance INTENDED
    ("D-IT", "5603", D("1500")),    # annual 18000 — INTENDED T-BUD-01 early
    ("D-MKT", "5602", D("750")),    # annual  9000 — Nov near-miss (no flag)
    ("D-QA", "5601", D("500")),     # annual  6000 — Aug near-miss (no flag)
]
TOTAL_BUDGET = D("69000")          # 5750 × 12 — hand-checked literal

# ============================================================ expenses (43)
# approval=""  → intentionally unapproved (T-EXP-02 target)
# attachment=False → intentionally missing document (T-EXP-01 target)
# Every amount/description is crafted against the seeded thresholds —
# see EXPECTED_EXCEPTIONS / MUST_NOT_FLAG at the bottom.
def _exp(number, day, dept, acc, amount, desc, *, supplier=None,
         invoice="", approval="APV", payment="transfer", attachment=True):
    return {
        "number": number, "date": day, "dept": dept, "acc": acc,
        "supplier": supplier, "desc": desc, "amount": D(amount),
        "payment": payment, "invoice": invoice, "approval": approval,
        "attachment": attachment,
    }


EXPENSES = [
    # ---- D-LOG / 5604 (budgeted 2000/mo): 11 × 4500 + Oct 19000 = 68500
    #      → T-BUD-01 Annual Overrun (intended) + Oct T-BUD-03 + T-EXP-04
    _exp("E-LOG-01", "2026-01-08", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L01"),
    _exp("E-LOG-02", "2026-02-09", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L02"),
    _exp("E-LOG-03", "2026-03-10", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L03"),
    _exp("E-LOG-04", "2026-04-07", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L04"),
    _exp("E-LOG-05", "2026-05-12", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L05"),
    _exp("E-LOG-06", "2026-06-11", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L06"),
    _exp("E-LOG-07", "2026-07-09", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L07"),
    _exp("E-LOG-08", "2026-08-13", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L08"),
    _exp("E-LOG-09", "2026-09-10", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L09"),
    # Oct: 19000 ≥ 4×4500 → T-EXP-04; month > 5000 → T-BUD-03;
    # description avoids purchase keywords → no T-EXP-06
    _exp("E-LOG-10", "2026-10-20", "D-LOG", "5604", "19000",
         "تغطية تكاليف تشغيل الربع الأخير", invoice="INV-L10"),
    _exp("E-LOG-11", "2026-11-06", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L11"),
    _exp("E-LOG-12", "2026-12-08", "D-LOG", "5604", "4500",
         "مستلزمات تشغيلية شهرية", invoice="INV-L12"),
    # ---- D-LOG / 5601 (budgeted 1000/mo): total 10000 — no BUD-01
    _exp("E-LTR-01", "2026-01-09", "D-LOG", "5601", "900",
         "شراء قطع غيار للمركبات", invoice="INV-T01"),
    # Feb total 3000 > 2500 and excess 2000 > 1500 → T-BUD-03 INTENDED
    # (SUPPLIES account — description must avoid travel keywords)
    _exp("E-LTR-02", "2026-02-05", "D-LOG", "5601", "3000",
         "تموين ومبيت الفريق الميداني", invoice="INV-T02"),
    _exp("E-LTR-03", "2026-04-14", "D-LOG", "5601", "1300",
         "تنقلات موظفين ميدانيين", invoice="INV-T03"),
    # shared-invoice pair (different suppliers → DB unique constraint OK)
    _exp("E-LTR-04", "2026-05-20", "D-LOG", "5601", "1800",
         "إقامة وتنقلات فريق التدريب", supplier="SUP-TRN-A",
         invoice="TRN-SHARE-11"),
    _exp("E-LTR-05", "2026-06-22", "D-LOG", "5601", "2200",
         "تنقلات مؤتمر سنوي", supplier="SUP-TRN-D",
         invoice="TRN-SHARE-11"),          # ← T-EXP-03 (invoice path)
    # NO attachment → T-EXP-01 INTENDED
    _exp("E-DOC1", "2026-12-08", "D-LOG", "5601", "800",
         "تنقلات نهاية العام", supplier="SUP-TRN-A",
         invoice="TRN-DOC-501", attachment=False),
    # ---- D-IT / 5603 (budgeted 1500/mo): 10 × 1800 = 18000
    #      → cum@Oct = 18000 ≥ 18000 and ≤ 18500 → T-BUD-01 early INTENDED
    *[
        _exp(f"E-ITS-{m:02d}", f"2026-{m:02d}-{12 + (m % 3):02d}",
             "D-IT", "5603", "1800", "اشتراك خدمات سحابية ودعم فني",
             invoice=f"INV-I{m:02d}")
        for m in range(1, 11)
    ],
    # ---- D-MKT / 5602 (budgeted 750/mo): total 3650
    _exp("E-MTR-01", "2026-09-07", "D-MKT", "5602", "1600",
         "سفر وتنقلات فريق التسويق", invoice="INV-M01"),
    # Nov 2050 ≤ 2250 → T-BUD-03 near-miss (must NOT flag)
    _exp("E-MTR-02", "2026-11-11", "D-MKT", "5602", "2050",
         "تنقلات معارض محلية", invoice="INV-M02"),
    # ---- D-QA / 5601 (budgeted 500/mo): total 4490 — no BUD-01, no early
    _exp("E-QSU-01", "2026-02-11", "D-QA", "5601", "700",
         "مستلزمات مكتبية للجودة", invoice="INV-Q01"),
    _exp("E-QSU-02", "2026-03-04", "D-QA", "5601", "500",
         "قرطاسية واختبارات", invoice="INV-Q02"),
    # own-category keyword (وقود → SUPPLIES = its own) → must NOT flag
    _exp("E-QSU-03", "2026-04-09", "D-QA", "5601", "600",
         "وقود مولدات المختبر", invoice="INV-Q03"),
    _exp("E-QSU-04", "2026-05-15", "D-QA", "5601", "700",
         "مستلزمات فحص وتجارب", invoice="INV-Q04"),
    # 1990 ≤ 2000 (BUD-03) and 1990 < 4×700 (EXP-04) → dual near-miss
    _exp("E-QSU-05", "2026-08-20", "D-QA", "5601", "1990",
         "تجهيزات مختبر الجودة", invoice="INV-Q05"),
    # ---- unbudgeted combinations → T-BUD-02 on EVERY row (8 rows)
    _exp("E-OB1", "2026-10-06", "D-IT", "5601", "1800",
         "مستلزمات مختبر التدريب", invoice="INV-OB1"),
    # PAYROLL description contains «سفر» → T-EXP-05 exclusion (no flag)
    _exp("E-OB2", "2026-07-15", "D-MKT", "5605", "4000",
         "رواتب وأجور شهر يوليو — سفر وتدريب", invoice="INV-OB2"),
    # UNAPPROVED → T-EXP-02 (Unapproved Payment)
    _exp("E-UNAP", "2026-09-12", "D-IT", "5602", "900",
         "خدمات استشارية تقنية", invoice="INV-UN1", approval=""),
    # D-IT/5602 (TRAVEL) is unbudgeted too — description carries no
    # keyword → EXP-05 stays quiet; cash ≥ 5000 → T-EXP-02 (Large Cash)
    _exp("E-CASH", "2026-11-03", "D-MKT", "5603", "6000",
         "خدمات إعلانية وحملات", invoice="INV-CS1", payment="cash"),
    # same supplier + same amount, gap 2 days, distinct invoices
    # → T-EXP-03 pair path flags the LATER row (E-DUP-B) only
    _exp("E-DUP-A", "2026-04-10", "D-QA", "5602", "1250",
         "مستلزمات فحص الجودة", supplier="SUP-TRN-B",
         invoice="TRN-INV-B410"),
    _exp("E-DUP-B", "2026-04-12", "D-QA", "5602", "1250",
         "مستلزمات فحص الجودة", supplier="SUP-TRN-B",
         invoice="TRN-INV-B412"),
    # description «فندق» maps to TRAVEL but category is SERVICES
    # → T-EXP-05 INTENDED
    _exp("E-CLS", "2026-05-15", "D-LOG", "5603", "850",
         "فندق وتنقلات للتدريب الداخلي", supplier="SUP-TRN-A",
         invoice="INV-CLS1"),
    # purchase keywords (شراء + أجهزة) with amount ≥ 1000 → T-EXP-06
    _exp("E-PUR", "2026-06-18", "D-QA", "5603", "2500",
         "شراء أجهزة حاسب للاختبارات", supplier="SUP-TRN-B",
         invoice="INV-PUR1"),
]

TOTAL_ACTUAL = D("123190")         # hand-checked literal (sum above)
OOB_COUNT = 8                      # rows on unbudgeted combinations
OOB_AMOUNT = D("18550")
VARIANCE = D("-54190")             # 69000 − 123190
UTILIZATION_FMT = "178.5"          # 123190 / 69000 × 100 → one decimal

# ============================================================ procurement (9)
def _proc(ref, day, dept, acc, supplier, amount, status, *, po="",
          approval="APV", quotes=()):
    return {
        "ref": ref, "date": day, "dept": dept, "acc": acc,
        "supplier": supplier, "amount": D(amount), "status": status,
        "po": po, "approval": approval,
        "quotes": [(s, D(a)) for s, a in quotes],
    }


_ACTIVE3 = [("SUP-TRN-A", "4900"), ("SUP-TRN-B", "5000"),
            ("SUP-TRN-D", "5100")]

PROCUREMENTS = [
    # clean control: 3 quotes + PO + approved + active supplier
    _proc("P-TRN-01", "2026-01-20", "D-IT", "5603", "SUP-TRN-A", "5000",
          "received", po="PO-2026-001", quotes=_ACTIVE3),
    # 0 quotes @3000 (PO present) → T-PROC-01 only
    _proc("P-TRN-02", "2026-02-10", "D-LOG", "5604", "SUP-TRN-B", "3000",
          "approved", po="PO-2026-002"),
    # no PO @800 (3 quotes) → T-PROC-02 only (below 1000 quote threshold)
    _proc("P-TRN-03", "2026-03-05", "D-MKT", "5602", "SUP-TRN-D", "800",
          "approved", quotes=_ACTIVE3),
    # pending → T-PROC-03 only
    _proc("P-TRN-04", "2026-04-12", "D-QA", "5601", "SUP-TRN-A", "2200",
          "pending", po="PO-2026-004", quotes=_ACTIVE3),
    # INACTIVE supplier (loaded bypassing form validation) → T-PROC-04
    _proc("P-TRN-05", "2026-05-08", "D-IT", "5603", "SUP-TRN-C", "1200",
          "approved", po="PO-2026-005", quotes=_ACTIVE3),
    # 15000 with 1 quote (PO present) → T-PROC-01 + T-PROC-05
    _proc("P-TRN-06", "2026-06-15", "D-LOG", "5601", "SUP-TRN-A", "15000",
          "approved", po="PO-2026-006",
          quotes=[("SUP-TRN-A", "15000")]),
    # @400 below every threshold (no PO, 2 quotes) → clean near-miss
    _proc("P-TRN-07", "2026-07-20", "D-MKT", "5602", "SUP-TRN-D", "400",
          "approved",
          quotes=[("SUP-TRN-A", "390"), ("SUP-TRN-B", "410")]),
    # draft + no PO @600 → T-PROC-02 + T-PROC-03
    _proc("P-TRN-08", "2026-08-14", "D-QA", "5601", "SUP-TRN-B", "600",
          "draft", quotes=_ACTIVE3),
    # cancelled @50000 / 0 quotes / no PO → control worked: MUST NOT flag
    _proc("P-TRN-09", "2026-09-10", "D-IT", "5603", "SUP-TRN-A", "50000",
          "cancelled"),
]

# ============================================================ ground truth
def _combo(dept, acc):
    return f"combo:{dept}:{acc}"


def _combo_m(dept, acc, month):
    return f"combo:{dept}:{acc}:m{month:02d}"


def _exp_s(number):
    return f"expense:{number}"


def _proc_s(ref):
    return f"proc:{ref}"


# (test_code, exception_type, subject) — EXACT engine output, pre-declared.
EXPECTED_EXCEPTIONS = frozenset({
    # ---- T-BUD-01 (2)
    ("T-BUD-01", "Annual Overrun", _combo("D-LOG", "5604")),
    ("T-BUD-01", "Early Consumption", _combo("D-IT", "5603")),
    # ---- T-BUD-02 (8) — every row on an unbudgeted combination
    ("T-BUD-02", "Out of Budget", _exp_s("E-OB1")),
    ("T-BUD-02", "Out of Budget", _exp_s("E-OB2")),
    ("T-BUD-02", "Out of Budget", _exp_s("E-UNAP")),
    ("T-BUD-02", "Out of Budget", _exp_s("E-CASH")),
    ("T-BUD-02", "Out of Budget", _exp_s("E-DUP-A")),
    ("T-BUD-02", "Out of Budget", _exp_s("E-DUP-B")),
    ("T-BUD-02", "Out of Budget", _exp_s("E-CLS")),
    ("T-BUD-02", "Out of Budget", _exp_s("E-PUR")),
    # ---- T-BUD-03 (2)
    ("T-BUD-03", "Unusual Monthly Variance", _combo_m("D-LOG", "5601", 2)),
    ("T-BUD-03", "Unusual Monthly Variance", _combo_m("D-LOG", "5604", 10)),
    # ---- T-EXP-01 (1)
    ("T-EXP-01", "Missing Supporting Document", _exp_s("E-DOC1")),
    # ---- T-EXP-02 (2)
    ("T-EXP-02", "Unapproved Payment", _exp_s("E-UNAP")),
    ("T-EXP-02", "Large Cash Payment", _exp_s("E-CASH")),
    # ---- T-EXP-03 (2) — pair path + shared-invoice path
    ("T-EXP-03", "Possible Duplicate Payment", _exp_s("E-DUP-B")),
    ("T-EXP-03", "Possible Duplicate Payment", _exp_s("E-LTR-05")),
    # ---- T-EXP-04 (1)
    ("T-EXP-04", "Unusual Amount", _exp_s("E-LOG-10")),
    # ---- T-EXP-05 (1)
    ("T-EXP-05", "Suspicious Classification", _exp_s("E-CLS")),
    # ---- T-EXP-06 (1)
    ("T-EXP-06", "Purchase without PO", _exp_s("E-PUR")),
    # ---- T-PROC-01 (2)
    ("T-PROC-01", "Insufficient Quotations", _proc_s("P-TRN-02")),
    ("T-PROC-01", "Insufficient Quotations", _proc_s("P-TRN-06")),
    # ---- T-PROC-02 (2)
    ("T-PROC-02", "Missing PO", _proc_s("P-TRN-03")),
    ("T-PROC-02", "Missing PO", _proc_s("P-TRN-08")),
    # ---- T-PROC-03 (2)
    ("T-PROC-03", "Incomplete Approval", _proc_s("P-TRN-04")),
    ("T-PROC-03", "Incomplete Approval", _proc_s("P-TRN-08")),
    # ---- T-PROC-04 (1)
    ("T-PROC-04", "Inactive Supplier", _proc_s("P-TRN-05")),
    # ---- T-PROC-05 (1)
    ("T-PROC-05", "High-Value Low Competition", _proc_s("P-TRN-06")),
})                                          # total = 28

EXPECTED_PER_TEST = {
    "T-BUD-01": 2, "T-BUD-02": 8, "T-BUD-03": 2,
    "T-PROC-01": 2, "T-PROC-02": 2, "T-PROC-03": 2,
    "T-PROC-04": 1, "T-PROC-05": 1,
    "T-EXP-01": 1, "T-EXP-02": 2, "T-EXP-03": 2,
    "T-EXP-04": 1, "T-EXP-05": 1, "T-EXP-06": 1,
}
EXPECTED_TOTAL = 28

# Subjects that MUST NOT appear under ANY test (clean + near-miss controls).
MUST_NOT_FLAG = (
    _proc_s("P-TRN-01"),          # 3 quotes + PO + approved + active
    _proc_s("P-TRN-07"),          # 400 < every procurement threshold
    _proc_s("P-TRN-09"),          # cancelled → excluded by 4 tests,
                                  #   active supplier → 5th stays quiet
    _exp_s("E-QSU-05"),           # 1990 ≤ 2000 (BUD-03) & < 4×700 (EXP-04)
    _exp_s("E-MTR-02"),           # 2050 ≤ 2250 (BUD-03 excess 1300 ≤ 1500)
    _exp_s("E-LTR-01"),           # «شراء» @900 < 1000 (EXP-06 floor)
    _exp_s("E-LTR-02"),           # clean supplies row (no EXP-05 keyword)
    _exp_s("E-QSU-03"),           # «وقود» on SUPPLIES = own category
    _exp_s("E-LOG-01"),           # plain budgeted row — never flagged
    _exp_s("E-QSU-01"),           # plain budgeted row — never flagged
)

# Additional targeted negatives (asserted as absence of a specific test key).
# Note: E-CASH IS flagged under T-EXP-02 — but only as "Large Cash Payment",
# never as "Unapproved Payment" (asserted explicitly in the tests).
TARGETED_NEGATIVES = (
    ("T-EXP-05", _exp_s("E-OB2")),    # PAYROLL exclusion clause
    ("T-EXP-06", _exp_s("E-LTR-01")),  # below po_min_amount
    ("T-EXP-04", _exp_s("E-QSU-05")),  # below 4× median
    ("T-EXP-01", _exp_s("E-QSU-01")),  # attachment present
    ("T-EXP-03", _exp_s("E-LTR-04")),  # shared-invoice ORIGINAL stays clean
    ("T-EXP-03", _exp_s("E-DUP-A")),   # earlier row of the pair stays clean
)

# Risk spot-checks: key → (risk_level, risk_rule_ref)  [classify_risk bands
# a3=10000 / a2=2000 from DB parameters]
RISK_SPOT_CHECKS = {
    ("T-BUD-01", _combo("D-LOG", "5604")): ("High", "RR-01"),
    ("T-BUD-01", _combo("D-IT", "5603")): ("Low", "RR-06"),
    ("T-BUD-03", _combo_m("D-LOG", "5601", 2)): ("Medium", "RR-04"),
    ("T-BUD-02", _exp_s("E-OB2")): ("High", "RR-02"),
    ("T-BUD-02", _exp_s("E-OB1")): ("Medium", "RR-03"),
    ("T-BUD-02", _exp_s("E-CLS")): ("Medium", "RR-03"),
    ("T-EXP-01", _exp_s("E-DOC1")): ("Low", "RR-05"),
    ("T-EXP-02", _exp_s("E-CASH")): ("High", "RR-02"),
    ("T-EXP-03", _exp_s("E-LTR-05")): ("High", "RR-02"),   # S3 + ≥2000
    ("T-EXP-06", _exp_s("E-PUR")): ("Medium", "RR-04"),
    ("T-PROC-01", _proc_s("P-TRN-06")): ("High", "RR-01"),
    ("T-PROC-04", _proc_s("P-TRN-05")): ("Low", "RR-05"),
}

RISK_COUNTS = {"High": 10, "Medium": 11, "Low": 7}


# ============================================================ loader
def load_training_dataset(*, verbosity: int = 0) -> dict:
    """Idempotently (re)create the whole synthetic dataset.

    Safe to re-run: business rows are keyed by their synthetic numbers and
    replaced atomically; dimensions/users are get_or_create'd. Returns a
    stats dict (also printed by the `load_training_dataset` command).
    """
    if settings.DEPLOYMENT_ENV == "production":
        raise ImproperlyConfigured(
            "Synthetic training data is never permitted in production."
        )
    if settings.DEPLOYMENT_ENV == "staging" and not settings.ALLOW_SYNTHETIC_DATASET:
        raise ImproperlyConfigured(
            "Set DJANGO_ALLOW_SYNTHETIC_DATASET=true only for an isolated staging database."
        )

    from apps.accounts.models import Role, UserRole
    from apps.budget.models import Budget, BudgetLine, BudgetVersion
    from apps.expenses.models import Expense
    from apps.procurement.models import Procurement, Quotation
    from apps.reference.models import (
        Account, Department, ExpenseCategory, FiscalYear, MonthlyPeriod,
        Supplier,
    )

    User = get_user_model()
    stats: dict = {"declaration": SYNTHETIC_DECLARATION}

    with transaction.atomic():
        # ---------------------------------------------------- users/roles
        users = {}
        for spec in USERS:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "is_staff": False,
                    "is_superuser": False,
                    "is_demo": True,
                },
            )
            fields_to_update = []
            if created:
                user.set_password(DS_PASSWORD)
                fields_to_update.append("password")
            if not user.is_demo:
                user.is_demo = True
                fields_to_update.append("is_demo")
            if fields_to_update:
                user.save(update_fields=fields_to_update)
            role = Role.objects.get(code=spec["role"])
            UserRole.objects.get_or_create(user=user, role=role)
            users[spec["username"]] = user

        # Keep the documented ``admin`` login as a stable convenience alias
        # for demonstrations while retaining ``ds_admin`` for dataset-owned
        # audit records and the original four role fixtures.
        demo_admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={"is_staff": True, "is_superuser": True, "is_demo": True},
        )
        admin_updates = []
        if not demo_admin.is_staff:
            demo_admin.is_staff = True
            admin_updates.append("is_staff")
        if not demo_admin.is_superuser:
            demo_admin.is_superuser = True
            admin_updates.append("is_superuser")
        if not demo_admin.is_demo:
            demo_admin.is_demo = True
            admin_updates.append("is_demo")
        if not demo_admin.check_password(ADMIN_PASSWORD):
            demo_admin.set_password(ADMIN_PASSWORD)
            admin_updates.append("password")
        if admin_updates:
            demo_admin.save(update_fields=admin_updates)
        UserRole.objects.get_or_create(user=demo_admin, role=Role.objects.get(code="admin"))
        stats["users"] = len(users)

        # ---------------------------------------------------- dimensions
        fy, _ = FiscalYear.objects.update_or_create(
            code=FISCAL_YEAR["code"], defaults=FISCAL_YEAR)
        for spec in DEPARTMENTS:
            Department.objects.update_or_create(
                code=spec["code"], defaults={**spec, "is_active": True})
        for spec in CATEGORIES:
            ExpenseCategory.objects.update_or_create(
                code=spec["code"], defaults={**spec, "is_active": True})
        cat_by = {c["code"]: ExpenseCategory.objects.get(code=c["code"])
                  for c in CATEGORIES}
        for spec in ACCOUNTS:
            Account.objects.update_or_create(
                code=spec["code"],
                defaults={"name": spec["name"], "account_type": "expense",
                          "expense_category": cat_by[spec["cat"]],
                          "is_active": True})
        for spec in SUPPLIERS:
            Supplier.objects.update_or_create(
                code=spec["code"], defaults={"name": spec["name"],
                                             "is_active": spec["is_active"]})
        stats.update({
            "fiscal_year": fy.code, "departments": len(DEPARTMENTS),
            "categories": len(CATEGORIES), "accounts": len(ACCOUNTS),
            "suppliers": len(SUPPLIERS),
        })

        # ---------------------------------------------------- periods
        for spec in MONTHLY_PERIODS:
            MonthlyPeriod.objects.update_or_create(
                fiscal_year=fy, month=spec["month"],
                defaults={"start_date": spec["start_date"],
                          "end_date": spec["end_date"],
                          "status": spec["status"], "is_active": True})
        stats["periods"] = 12

        dept_by = {d["code"]: Department.objects.get(code=d["code"])
                   for d in DEPARTMENTS}
        acc_by = {a["code"]: Account.objects.get(code=a["code"])
                  for a in ACCOUNTS}
        sup_by = {s["code"]: Supplier.objects.get(code=s["code"])
                  for s in SUPPLIERS}
        period_of = {p.month: p for p in
                     MonthlyPeriod.objects.filter(fiscal_year=fy)}

        # ---------------------------------------------------- budget
        # One budget per FY (OneToOne) — reuse if a budget already exists
        # (e.g. demo seed); our five lines are created/replaced below.
        budget, _ = Budget.objects.get_or_create(
            fiscal_year=fy, defaults={"name": BUDGET_NAME})
        version, _ = BudgetVersion.objects.get_or_create(
            budget=budget, version=1,
            defaults={"status": "approved",
                      "approved_by": users["ds_admin"]})
        if version.status != "approved":
            version.status = "approved"
            version.approved_by = users["ds_admin"]
            version.save(update_fields=["status", "approved_by",
                                        "updated_at"])
        month_fields = [f"m{m:02d}" for m in range(1, 13)]
        for spec in BUDGET_LINES:
            dept, acc, monthly = spec
            line = BudgetLine.objects.filter(
                version=version, department=dept_by[dept],
                account=acc_by[acc]).first()
            if line is None:
                line = BudgetLine(version=version, department=dept_by[dept],
                                  account=acc_by[acc],
                                  created_by=users["ds_finance"])
            line.expense_category = acc_by[acc].expense_category
            for fname in month_fields:
                setattr(line, fname, monthly)
            line.full_clean()      # derives annual_amount + validates
            line.save()
        stats["budget_lines"] = BudgetLine.objects.filter(
            version=version).count()

        # ---------------------------------------------------- expenses
        numbers = [row["number"] for row in EXPENSES]
        Expense.objects.filter(expense_number__in=numbers).delete()
        finance, admin = users["ds_finance"], users["ds_admin"]
        for row in EXPENSES:
            d = date.fromisoformat(row["date"])
            e = Expense(
                expense_number=row["number"],
                expense_date=d,
                period=period_of[d.month],
                department=dept_by[row["dept"]],
                account=acc_by[row["acc"]],
                expense_category=acc_by[row["acc"]].expense_category,
                supplier=(sup_by[row["supplier"]] if row["supplier"]
                          else None),
                description=row["desc"],
                amount=row["amount"],
                currency="USD",
                payment_method=row["payment"],
                invoice_reference=row["invoice"] or None,
                approval_reference=row["approval"],
                approved_by=(admin if row["approval"] else None),
                created_by=finance,
            )
            if row["attachment"]:
                e.attachment.save(
                    f"{row['number']}.pdf",
                    ContentFile(b"%PDF-1.4 synthetic training document"),
                    save=False)
            e.save()
        stats["expenses"] = len(EXPENSES)

        # ---------------------------------------------------- procurement
        refs = [row["ref"] for row in PROCUREMENTS]
        Procurement.objects.filter(reference_number__in=refs).delete()
        for row in PROCUREMENTS:
            d = date.fromisoformat(row["date"])
            # NOTE: created with objects.create (no form) because
            # P-TRN-05 deliberately carries an inactive supplier — the
            # engine must see that state; entry forms would reject it.
            p = Procurement.objects.create(
                reference_number=row["ref"],
                date=d,
                department=dept_by[row["dept"]],
                supplier=sup_by[row["supplier"]],
                account=acc_by[row["acc"]],
                expense_category=acc_by[row["acc"]].expense_category,
                description=f"سجل مشتريات تدريبي {row['ref']}",
                amount=row["amount"],
                status=row["status"],
                purchase_order=row["po"],
                approval_reference=row["approval"],
                created_by=finance,
            )
            for sup_code, amount in row["quotes"]:
                Quotation.objects.create(
                    procurement=p, supplier=sup_by[sup_code],
                    amount=amount, offer_date=d)
        stats["procurements"] = len(PROCUREMENTS)
        stats["quotations"] = Quotation.objects.filter(
            procurement__reference_number__in=refs).count()

    return stats
