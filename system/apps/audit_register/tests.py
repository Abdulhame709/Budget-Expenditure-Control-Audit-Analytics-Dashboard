"""PHASE 9 — Audit Test Engine tests: seeded metadata contract, the 14
evaluators (flagged + pass), risk matrix, run storage/traceability, DB-driven
thresholds, RBAC — Synthetic Training data only.
"""
from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import ALL_CODES, PERMISSIONS, URL_PERMISSIONS
from apps.audit_register import services as engine
from apps.audit_register.models import (
    AuditException,
    AuditRun,
    AuditTest,
    AuditTestResult,
)
from apps.budget.models import Budget, BudgetVersion, BudgetLine
from apps.expenses.models import Expense
from apps.governance.models import AuditLog
from apps.procurement.models import Procurement, Quotation
from apps.reference.models import (
    Account,
    Department,
    ExpenseCategory,
    FiscalYear,
    MonthlyPeriod,
    Supplier,
)

User = get_user_model()
PW = "S3cure-Demo-Pass!"
TEMP_MEDIA = tempfile.mkdtemp(prefix="p9_media_")

EXPECTED_CODES = [
    "T-BUD-01", "T-BUD-02", "T-BUD-03",
    "T-PROC-01", "T-PROC-02", "T-PROC-03", "T-PROC-04", "T-PROC-05",
    "T-EXP-01", "T-EXP-02", "T-EXP-03", "T-EXP-04", "T-EXP-05", "T-EXP-06",
]


def make_user(username, role_code):
    user = User.objects.create_user(username=username, password=PW)
    UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


class BaseFixture(TestCase):
    """Shared dimensions + users. Seeded 14 tests come from the migration."""

    @classmethod
    def setUpTestData(cls):
        cls.fy = FiscalYear.objects.create(
            code="FY2026", name="2026", year=2026,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        cls.p_jan = MonthlyPeriod.objects.create(
            fiscal_year=cls.fy, month=1, start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31))
        cls.p_feb = MonthlyPeriod.objects.create(
            fiscal_year=cls.fy, month=2, start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28))
        cls.dept_ops = Department.objects.create(code="OPS", name="العمليات")
        cls.dept_fin = Department.objects.create(
            code="FINANCE", name="المالية")
        cls.dept_adm = Department.objects.create(code="ADMIN", name="الإدارة")
        cls.cat_s = ExpenseCategory.objects.create(
            code="SUPPLIES", name="مستلزمات")
        cls.cat_t = ExpenseCategory.objects.create(code="TRAVEL", name="سفر")
        cls.acc5102 = Account.objects.create(
            code="5102", name="مستلزمات", account_type="expense",
            expense_category=cls.cat_s)
        cls.acc5210 = Account.objects.create(
            code="5210", name="سفر", account_type="expense",
            expense_category=cls.cat_t)
        cls.acc5310 = Account.objects.create(
            code="5310", name="خدمات", account_type="expense",
            expense_category=cls.cat_s)
        cls.sup1 = Supplier.objects.create(code="SUP-01", name="مورد أ")
        cls.sup2 = Supplier.objects.create(code="SUP-02", name="مورد ب")
        cls.auditor = make_user("aud_p9", "auditor")
        cls.finance = make_user("fin_p9", "finance")
        cls.mgmt = make_user("mgmt_p9", "management")

    def exp(self, *, dept, acc, amount, d, invoice="", supplier=None,
            desc="بيان", approval=False, payment="transfer",
            currency="USD", attachment=False, number=""):
        e = Expense.objects.create(
            expense_number=number,
            expense_date=d,
            period=MonthlyPeriod.objects.get(
                start_date__lte=d, end_date__gte=d),
            department=dept, account=acc,
            expense_category=acc.expense_category,
            supplier=supplier, description=desc, amount=D(str(amount)),
            currency=currency, payment_method=payment,
            invoice_reference=invoice or None,
            approval_reference=("DEC-1" if approval else ""),
            created_by=self.finance)
        if attachment:
            e.attachment.save("doc.pdf", ContentFile(b"%PDF-1.4 x"),
                              save=True)
        return e

    def approved_budget(self, lines):
        bud = Budget.objects.create(fiscal_year=self.fy, name="ميزانية")
        ver = BudgetVersion.objects.create(
            budget=bud, version=1, status="approved")
        for dept, acc, months in lines:
            line = BudgetLine(version=ver, department=dept, account=acc,
                              created_by=self.finance, **months)
            line.full_clean()
            line.save()
        return ver

    def get_test(self, code):
        return AuditTest.objects.get(test_code=code)

    def run_one(self, code, user=None):
        return engine.start_run(
            [self.get_test(code)], user or self.auditor, mode="single")

    def exceptions_of(self, run):
        return list(run.exceptions.order_by("pk"))


# ================================================================ metadata
class SeedMetadataTests(TestCase):
    def test_fourteen_tests_seeded(self):
        self.assertEqual(AuditTest.objects.count(), 14)
        self.assertEqual(
            sorted(AuditTest.objects.values_list("test_code", flat=True)),
            sorted(EXPECTED_CODES))

    def test_every_required_field_present(self):
        for t in AuditTest.objects.all():
            for field in ("test_code", "name", "objective", "rule_text",
                          "data_source", "expected_result", "exception_type",
                          "default_risk", "auditor_action", "engine_key"):
                self.assertTrue(
                    getattr(t, field), f"{t.test_code}.{field} فارغ")
            self.assertTrue(t.parameters)
            self.assertTrue(t.is_active)
            self.assertTrue(t.synthetic_rule)
            self.assertIn("Synthetic/Training Rule", t.rule_text)
            self.assertTrue(t.parameters.get("risk_bands"))
            self.assertIn(t.engine_key, engine.EVALUATORS)
            self.assertTrue(t.parameters.get("synthetic_rule") is True)

    def test_parameters_are_db_managed_thresholds(self):
        proc01 = AuditTest.objects.get(test_code="T-PROC-01")
        self.assertEqual(proc01.parameters["min_quotes"], 3)
        self.assertEqual(proc01.parameters["min_amount"], 1000)
        exp02 = AuditTest.objects.get(test_code="T-EXP-02")
        self.assertEqual(exp02.parameters["large_cash"], 5000)
        exp05 = AuditTest.objects.get(test_code="T-EXP-05")
        self.assertIn("keyword_map", exp05.parameters)
        self.assertIn("TRAVEL", exp05.parameters["keyword_map"])


# ================================================================ budget engine
class EngineBudgetTests(BaseFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ver = cls._budget()

    @classmethod
    def _budget(cls):
        bud = Budget.objects.create(fiscal_year=cls.fy, name="ميزانية")
        ver = BudgetVersion.objects.create(
            budget=bud, version=1, status="approved")
        specs = [
            (cls.dept_ops, cls.acc5102, {"m01": D("1000")}),       # 1000
            (cls.dept_fin, cls.acc5210, {"m01": D("10000")}),      # 10000
            (cls.dept_adm, cls.acc5310, {"m02": D("400")}),        # 400
        ]
        for dept, acc, months in specs:
            line = BudgetLine(version=ver, department=dept, account=acc,
                              **months)
            line.full_clean()
            line.save()
        return ver

    def setUp(self):
        # designed dataset
        self.a = self.exp(dept=self.dept_ops, acc=self.acc5102, amount=1700,
                          d=date(2026, 1, 10), invoice="B1",
                          supplier=self.sup1, number="EA")
        self.b = self.exp(dept=self.dept_fin, acc=self.acc5210, amount=10000,
                          d=date(2026, 1, 12), invoice="B2",
                          supplier=self.sup1, number="EB")
        self.c = self.exp(dept=self.dept_adm, acc=self.acc5310, amount=2000,
                          d=date(2026, 2, 5), invoice="B3",
                          supplier=self.sup1, number="EC")
        self.d = self.exp(dept=self.dept_ops, acc=self.acc5310, amount=300,
                          d=date(2026, 1, 15), invoice="B4",
                          supplier=self.sup2, number="ED")
        self.e_yer = self.exp(dept=self.dept_ops, acc=self.acc5310,
                              amount=99999, d=date(2026, 1, 16),
                              supplier=self.sup1, currency="YER",
                              number="EY")

    def test_bud01_overrun_and_early(self):
        checked, findings = engine.eval_budget_overrun_early(
            self.get_test("T-BUD-01"), self.get_test("T-BUD-01").parameters)
        self.assertEqual(checked, 3)  # three budgeted combos
        by_type = {}
        for f in findings:
            by_type.setdefault(f["exception_type"], []).append(f)
        self.assertEqual(len(by_type["Annual Overrun"]), 2)   # OPS, ADMIN
        self.assertEqual(len(by_type["Early Consumption"]), 1)  # FINANCE
        sources = {f["source_id"] for f in findings}
        self.assertIn(f"{self.dept_ops.pk}|{self.acc5102.pk}", sources)
        self.assertIn(f"{self.dept_fin.pk}|{self.acc5210.pk}", sources)
        # explanation carries actual vs budget
        overrun = [f for f in findings
                   if f["exception_type"] == "Annual Overrun"][0]
        self.assertIn("تجاوز", overrun["description"])

    def test_bud02_out_of_budget_only_usd(self):
        checked, findings = engine.eval_budget_coverage(
            self.get_test("T-BUD-02"), self.get_test("T-BUD-02").parameters)
        self.assertEqual(checked, 4)  # USD expenses only
        self.assertEqual([f["source_id"] for f in findings], [str(self.d.pk)])
        self.assertEqual(findings[0]["exception_type"], "Out of Budget")
        self.assertNotIn(str(self.e_yer.pk),
                         [f["source_id"] for f in findings])

    def test_bud03_monthly_variance_thresholds(self):
        checked, findings = engine.eval_monthly_variance(
            self.get_test("T-BUD-03"), self.get_test("T-BUD-03").parameters)
        self.assertEqual(checked, 3)  # (OPS Jan, FIN Jan, ADMIN Feb) present
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["source_id"],
                         f"{self.dept_adm.pk}|{self.acc5310.pk}|02")
        self.assertIn("الشهر 02", findings[0]["description"])

    def test_budget_engines_pass_on_clean_data(self):
        Expense.objects.all().delete()
        self.exp(dept=self.dept_ops, acc=self.acc5102, amount=500,
                 d=date(2026, 1, 20), invoice="C1", supplier=self.sup2,
                 number="EZ")
        for code, fn in (("T-BUD-01", engine.eval_budget_overrun_early),
                         ("T-BUD-02", engine.eval_budget_coverage),
                         ("T-BUD-03", engine.eval_monthly_variance)):
            t = self.get_test(code)
            checked, findings = fn(t, t.parameters)
            self.assertEqual(findings, [], code)


# ================================================================ procurement engine
class EngineProcTests(BaseFixture):
    def setUp(self):
        self.p1 = Procurement.objects.create(
            reference_number="PR-A1", date=date(2026, 1, 5),
            department=self.dept_ops, supplier=self.sup1, account=self.acc5102,
            description="أجهزة خوادم", amount=D("12000"), status="approved",
            purchase_order="PO-1", created_by=self.finance)
        for i, sup in enumerate([self.sup1, self.sup2], start=1):
            Quotation.objects.create(
                procurement=self.p1, supplier=sup,
                amount=D(str(11500 + i)))
        self.p2 = Procurement.objects.create(
            reference_number="PR-A2", date=date(2026, 1, 8),
            department=self.dept_adm, supplier=self.sup2, account=self.acc5310,
            description="صيانة دورية", amount=D("600"), status="draft",
            created_by=self.finance)                     # no PO, 0 quotes
        self.sup_dead = Supplier.objects.create(
            code="SUP-D", name="مورد معطّل", is_active=False)
        self.p3 = Procurement.objects.create(
            reference_number="PR-A3", date=date(2026, 2, 2),
            department=self.dept_fin, supplier=self.sup_dead,
            account=self.acc5210, description="نقل", amount=D("400"),
            status="received", purchase_order="PO-3", created_by=self.finance)
        self.p4 = Procurement.objects.create(
            reference_number="PR-A4", date=date(2026, 2, 6),
            department=self.dept_ops, supplier=self.sup1, account=self.acc5102,
            description="ترخيص برنامج", amount=D("5000"), status="approved",
            purchase_order="PO-4", created_by=self.finance)
        for sup in (self.sup1, self.sup2):
            Quotation.objects.create(procurement=self.p4, supplier=sup,
                                     amount=D("5000"))
            Quotation.objects.create(procurement=self.p4,
                                     supplier=Supplier.objects.create(
                                         code=f"X{sup.pk}", name=f"ز{sup.pk}"),
                                     amount=D("5100"))
        self.p5 = Procurement.objects.create(   # cancelled — excluded
            reference_number="PR-A5", date=date(2026, 2, 9),
            department=self.dept_ops, supplier=self.sup1, account=self.acc5102,
            description="ملغى كبير", amount=D("50000"), status="cancelled",
            created_by=self.finance)

    def _findings(self, code):
        t = self.get_test(code)
        fn = engine.EVALUATORS[t.engine_key]
        checked, findings = fn(t, t.parameters)
        return checked, findings

    def test_proc01_insufficient_quotes(self):
        checked, findings = self._findings("T-PROC-01")
        self.assertEqual(checked, 4)  # cancelled excluded
        self.assertEqual([f["source_id"] for f in findings], [str(self.p1.pk)])
        self.assertIn("عروض 2", findings[0]["description"])

    def test_proc02_missing_po(self):
        checked, findings = self._findings("T-PROC-02")
        self.assertEqual([f["source_id"] for f in findings], [str(self.p2.pk)])
        self.assertEqual(findings[0]["exception_type"], "Missing PO")
        self.assertNotIn(str(self.p5.pk),
                         [f["source_id"] for f in findings])

    def test_proc03_pending_approval(self):
        checked, findings = self._findings("T-PROC-03")
        self.assertEqual([f["source_id"] for f in findings], [str(self.p2.pk)])

    def test_proc04_inactive_supplier(self):
        checked, findings = self._findings("T-PROC-04")
        self.assertEqual([f["source_id"] for f in findings], [str(self.p3.pk)])
        self.assertIn("معطّل", findings[0]["description"])

    def test_proc05_high_value_low_competition(self):
        checked, findings = self._findings("T-PROC-05")
        self.assertEqual([f["source_id"] for f in findings], [str(self.p1.pk)])
        self.assertEqual(findings[0]["exception_type"],
                         "High-Value Low Competition")

    def test_proc_engines_pass_clean(self):
        Procurement.objects.all().delete()
        p = Procurement.objects.create(
            reference_number="PR-CLEAN", date=date(2026, 1, 3),
            department=self.dept_ops, supplier=self.sup1, account=self.acc5102,
            description="نظيف", amount=D("3000"), status="received",
            purchase_order="PO-C", created_by=self.finance)
        for sup, amt in ((self.sup1, D("3000")), (self.sup2, D("3100"))):
            third = Supplier.objects.create(code=f"C{sup.pk}", name=f"ج{sup.pk}")
            Quotation.objects.create(procurement=p, supplier=sup, amount=amt)
            Quotation.objects.create(procurement=p, supplier=third,
                                     amount=amt + 100)
        for code in ("T-PROC-01", "T-PROC-02", "T-PROC-03",
                     "T-PROC-04", "T-PROC-05"):
            t = self.get_test(code)
            _, findings = engine.EVALUATORS[t.engine_key](t, t.parameters)
            self.assertEqual(findings, [], code)


# ================================================================ expense engine
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class EngineExpTests(BaseFixture):
    def setUp(self):
        # supporting docs
        self.no_doc = self.exp(dept=self.dept_ops, acc=self.acc5102,
                               amount=150, d=date(2026, 1, 5),
                               invoice="D1", supplier=self.sup1,
                               desc="بدون مستند", number="E1")
        self.doc = self.exp(dept=self.dept_ops, acc=self.acc5102,
                            amount=160, d=date(2026, 1, 6), invoice="D2",
                            supplier=self.sup1, desc="بمستند",
                            attachment=True, number="E2")
        # payment controls
        self.unapproved = self.exp(dept=self.dept_fin, acc=self.acc5210,
                                   amount=700, d=date(2026, 1, 7),
                                   invoice="D3", supplier=self.sup2,
                                   desc="غير معتمد", number="E3")
        self.cash_big = self.exp(dept=self.dept_fin, acc=self.acc5210,
                                 amount=6000, d=date(2026, 1, 8),
                                 invoice="D4", supplier=self.sup2,
                                 desc="نقدي كبير", approval=True,
                                 payment="cash", number="E4")
        # duplicates: supplier+amount pair
        self.dup1 = self.exp(dept=self.dept_ops, acc=self.acc5310,
                             amount=500, d=date(2026, 1, 9), invoice="DA",
                             supplier=self.sup1, desc="أصل", number="E5")
        self.dup2 = self.exp(dept=self.dept_ops, acc=self.acc5310,
                             amount=500, d=date(2026, 1, 11), invoice="DB",
                             supplier=self.sup1, desc="مكرر", number="E6")
        # duplicates: shared invoice across suppliers
        self.inv1 = self.exp(dept=self.dept_adm, acc=self.acc5310,
                             amount=300, d=date(2026, 1, 12),
                             invoice="INV-X", supplier=self.sup1,
                             desc="فاتورة مشتركة", number="E7")
        self.inv2 = self.exp(dept=self.dept_adm, acc=self.acc5310,
                             amount=700, d=date(2026, 1, 13),
                             invoice="INV-X", supplier=self.sup2,
                             desc="فاتورة مشتركة 2", number="E8")
        # unusual amounts — peers on OPS/5102 (median 100 among 5... careful
        # no_doc/doc are also OPS/5102: amounts 150,160 + below set)
        self.peer = [self.exp(dept=self.dept_ops, acc=self.acc5102,
                              amount=100, d=date(2026, 1, day),
                              invoice=f"P{day}", supplier=self.sup2,
                              desc="peer", number=f"U{day}")
                     for day in (14, 15, 16, 17)]
        self.big = self.exp(dept=self.dept_ops, acc=self.acc5102,
                            amount=700, d=date(2026, 1, 18), invoice="PB",
                            supplier=self.sup2, desc="غير معتاد",
                            number="E9")
        # classification
        self.cls_ok = self.exp(dept=self.dept_fin, acc=self.acc5210,
                               amount=400, d=date(2026, 2, 2),
                               invoice="CL1", supplier=self.sup1,
                               desc="hotel booking trip", number="E10")
        self.cls_bad = self.exp(dept=self.dept_ops, acc=self.acc5102,
                                amount=450, d=date(2026, 2, 3),
                                invoice="CL2", supplier=self.sup1,
                                desc="hotel invoice for office", number="E11")
        # purchase without PO
        self.buy = self.exp(dept=self.dept_adm, acc=self.acc5102,
                            amount=1500, d=date(2026, 2, 8), invoice="PO1",
                            supplier=self.sup2,
                            desc="Purchase of laptops", number="E12")
        self.pay_for = self.exp(dept=self.dept_adm, acc=self.acc5102,
                                amount=1500, d=date(2026, 2, 9), invoice="PO2",
                                supplier=self.sup2,
                                desc="Payment for supplier balance",
                                number="E13")
        self.small_buy = self.exp(dept=self.dept_adm, acc=self.acc5102,
                                  amount=800, d=date(2026, 2, 10),
                                  invoice="PO3", supplier=self.sup2,
                                  desc="purchase of chairs", number="E14")
        # YER cash — must be excluded from USD tests (unapproved + big cash:
        # would flag both control types if the currency filter leaked)
        self.yer_cash = self.exp(dept=self.dept_fin, acc=self.acc5210,
                                 amount=99999, d=date(2026, 2, 11),
                                 invoice="Y1", supplier=self.sup2,
                                 desc="نقدي يمني",
                                 payment="cash", currency="YER",
                                 number="E15")

    def _findings(self, code):
        t = self.get_test(code)
        return engine.EVALUATORS[t.engine_key](t, t.parameters)

    def test_exp01_missing_document(self):
        checked, findings = self._findings("T-EXP-01")
        ids = [f["source_id"] for f in findings]
        self.assertIn(str(self.no_doc.pk), ids)
        self.assertNotIn(str(self.doc.pk), ids)
        self.assertNotIn(str(self.yer_cash.pk), ids)

    def test_exp02_payment_controls_two_types(self):
        checked, findings = self._findings("T-EXP-02")
        pairs = {f["source_id"]: f["exception_type"] for f in findings}
        self.assertEqual(pairs.get(str(self.unapproved.pk)),
                         "Unapproved Payment")
        self.assertEqual(pairs.get(str(self.cash_big.pk)),
                         "Large Cash Payment")
        self.assertNotIn(str(self.yer_cash.pk), pairs)

    def test_exp03_duplicate_pairs_trace_to_original(self):
        checked, findings = self._findings("T-EXP-03")
        by_src = {f["source_id"]: f for f in findings}
        self.assertIn(str(self.dup2.pk), by_src)
        self.assertNotIn(str(self.dup1.pk), by_src)
        self.assertEqual(by_src[str(self.dup2.pk)]["source_ref"]
                         ["original_id"], self.dup1.pk)
        self.assertIn("بنفس المورد والمبلغ",
                      by_src[str(self.dup2.pk)]["description"])
        self.assertIn(str(self.inv2.pk), by_src)
        self.assertIn("بنفس رقم الفاتورة INV-X",
                      by_src[str(self.inv2.pk)]["description"])

    def test_exp04_unusual_amount_vs_median(self):
        checked, findings = self._findings("T-EXP-04")
        ids = [f["source_id"] for f in findings]
        # OPS/5102 peers: [100,100,100,100,150,160,700] median=100 → only 700
        # (≥ 500 floor AND ≥ 4×median) qualifies.
        self.assertIn(str(self.big.pk), ids)
        self.assertNotIn(str(self.no_doc.pk), ids)
        self.assertNotIn(str(self.doc.pk), ids)
        self.assertNotIn(str(self.peer[0].pk), ids)
        self.assertNotIn(str(self.yer_cash.pk), ids)

    def test_exp05_classification_keyword_map(self):
        checked, findings = self._findings("T-EXP-05")
        ids = [f["source_id"] for f in findings]
        self.assertIn(str(self.cls_bad.pk), ids)   # hotel → TRAVEL ≠ SUPPLIES
        self.assertNotIn(str(self.cls_ok.pk), ids)  # hotel → TRAVEL == TRAVEL
        self.assertIn("TRAVEL", findings[0]["description"])

    def test_exp06_purchase_without_po(self):
        checked, findings = self._findings("T-EXP-06")
        ids = [f["source_id"] for f in findings]
        self.assertIn(str(self.buy.pk), ids)
        self.assertNotIn(str(self.pay_for.pk), ids)
        self.assertNotIn(str(self.small_buy.pk), ids)  # < 1000


# ================================================================ risk matrix
class RiskMatrixTests(TestCase):
    def test_approved_3x3_matrix(self):
        bands = {"risk_bands": {"a3": 10000, "a2": 2000}}
        cases = [
            (10000, "S2", "High", "RR-01"),
            (15000, "S1", "High", "RR-01"),
            (2500, "S3", "High", "RR-02"),
            (2500, "S2", "Medium", "RR-04"),
            (300, "S3", "Medium", "RR-03"),
            (300, "S2", "Low", "RR-05"),
            (300, "S1", "Low", "RR-06"),
        ]
        for amount, sev, risk, ref in cases:
            self.assertEqual(engine.classify_risk(amount, sev, bands),
                             (risk, ref), (amount, sev))

    def test_bands_come_from_db_parameters(self):
        custom = {"risk_bands": {"a3": 500, "a2": 100}}
        self.assertEqual(engine.classify_risk(600, "S1", custom),
                         ("High", "RR-01"))


# ================================================================ run engine
class RunEngineTests(BaseFixture):
    def test_single_run_stores_everything(self):
        p = Procurement.objects.create(
            reference_number="PR-R1", date=date(2026, 1, 5),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="بدون عروض",
            amount=D("2000"), status="approved",
            created_by=self.finance)   # 0 quotes, ≥1000 → flagged
        run = self.run_one("T-PROC-01")
        self.assertEqual(run.run_number, "AR-2026-00001")
        self.assertEqual(run.status, AuditRun.STATUS_COMPLETED)
        self.assertEqual(run.tests_total, 1)
        self.assertEqual(run.tests_flagged, 1)
        self.assertEqual(run.exceptions_total, 1)
        result = run.results.get()
        self.assertEqual(result.status, AuditTestResult.STATUS_FLAGGED)
        self.assertEqual(result.records_checked, 1)
        self.assertEqual(result.params_snapshot,
                         self.get_test("T-PROC-01").parameters)
        exc = run.exceptions.get()
        self.assertEqual(exc.source_type, "procurement")
        self.assertEqual(exc.source_id, str(p.pk))
        self.assertTrue(exc.explanation)
        self.assertTrue(exc.risk_rule_ref.startswith("RR-"))
        self.assertEqual(exc.test_code, "T-PROC-01")
        # traceability → real transaction + its detail URL
        self.assertTrue(
            Procurement.objects.filter(pk=int(exc.source_id)).exists())
        self.assertEqual(
            reverse("procurement:detail", args=[exc.source_id]),
            f"/procurement/{p.pk}/")
        # audit rows
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="audit_run",
            entity_id=str(run.pk)).exists())
        self.assertTrue(AuditLog.objects.filter(
            action="entity_updated", entity_type="audit_run",
            entity_id=str(run.pk)).exists())

    def test_run_all_active_and_inactive_skipped(self):
        run = engine.start_run(
            AuditTest.objects.filter(is_active=True), self.auditor,
            mode=AuditRun.MODE_ALL)
        self.assertEqual(run.tests_total, 14)
        self.assertEqual(run.tests_pass + run.tests_flagged + run.tests_fail,
                         14)
        self.assertEqual(run.results.count(), 14)
        # empty data → everything passes
        self.assertEqual(run.tests_flagged, 0)
        self.assertEqual(run.tests_pass, 14)
        # deactivate one → all-active runs 13
        t = self.get_test("T-EXP-03")
        t.is_active = False
        t.save()
        run2 = engine.start_run(
            AuditTest.objects.filter(is_active=True), self.auditor,
            mode=AuditRun.MODE_ALL)
        self.assertEqual(run2.tests_total, 13)
        # selected may still run the inactive test explicitly
        run3 = engine.start_run([t], self.auditor, mode="selected")
        self.assertEqual(run3.tests_total, 1)

    def test_unknown_engine_key_fails_gracefully(self):
        t = AuditTest.objects.create(
            test_code="T-X-99", name="محرك مفقود", domain="general",
            objective="o", rule_text="r", data_source="d",
            expected_result="e", exception_type="x",
            auditor_action="a", engine_key="missing_engine")
        run = self.run_one("T-X-99")
        result = run.results.get()
        self.assertEqual(result.status, AuditTestResult.STATUS_FAIL)
        self.assertIn("لا يوجد منفّذ", result.error)
        self.assertEqual(run.tests_fail, 1)
        self.assertEqual(run.status, AuditRun.STATUS_FAILED)

    def test_threshold_edit_in_db_changes_outcome(self):
        Procurement.objects.create(
            reference_number="PR-R2", date=date(2026, 1, 6),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="600 بلا عروض",
            amount=D("600"), status="approved", created_by=self.finance)
        run1 = self.run_one("T-PROC-01")        # min_amount=1000 → pass
        self.assertEqual(run1.tests_pass, 1)
        t = self.get_test("T-PROC-01")
        t.parameters["min_amount"] = 500         # DB edit — not code
        t.save()
        run2 = self.run_one("T-PROC-01")
        self.assertEqual(run2.tests_flagged, 1)  # now flagged
        self.assertEqual(run2.exceptions.get().amount, D("600"))

    def test_pass_result_explains_why(self):
        run = self.run_one("T-PROC-04")          # all suppliers active
        result = run.results.get()
        self.assertEqual(result.status, AuditTestResult.STATUS_PASS)
        self.assertIn("نجح", result.explanation)
        self.assertEqual(result.exceptions_count, 0)

    def test_risk_levels_stored_on_exceptions(self):
        p = Procurement.objects.create(
            reference_number="PR-R3", date=date(2026, 1, 7),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="عالي القيمة بلا عروض",
            amount=D("15000"), status="approved", created_by=self.finance)
        run = self.run_one("T-PROC-05")
        exc = run.exceptions.get()
        self.assertEqual(exc.risk_level, "High")     # ≥ a3
        self.assertEqual(exc.risk_rule_ref, "RR-01")
        self.assertEqual(exc.control_severity, "S2")


# ================================================================ HTTP
class HttpEngineTests(BaseFixture):
    def _c(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_rbac(self):
        # finance: no audit.* codes at all
        self.assertEqual(
            self._c(self.finance).get(
                reverse("audit:tests_list")).status_code, 403)
        self.assertEqual(
            self._c(self.finance).post(
                reverse("audit:run_start"), {"mode": "all_active"}
            ).status_code, 403)
        # management: read-only exceptions.view (approved matrix) — no audit.*
        self.assertEqual(
            self._c(self.mgmt).get(
                reverse("audit:tests_list")).status_code, 403)
        self.assertEqual(
            self._c(self.mgmt).get(
                reverse("audit:exceptions_list")).status_code, 200)
        # auditor holds audit.view/run/rules.manage + exceptions.*
        self.assertEqual(
            self._c(self.auditor).get(
                reverse("audit:tests_list")).status_code, 200)
        response = self.client.get(reverse("audit:tests_list"))
        self.assertEqual(response.status_code, 302)

    def test_tests_list_hides_training_badge_in_operational_mode(self):
        response = self._c(self.auditor).get(reverse("audit:tests_list"))
        self.assertContains(response, "T-EXP-03")
        self.assertNotContains(response, "Synthetic Rule")
        self.assertContains(response, "تخضع للمراجعة والاعتماد")
        self.assertContains(response, "تشغيل كل الاختبارات المفعّلة")

    def test_run_all_via_http(self):
        c = self._c(self.auditor)
        response = c.post(reverse("audit:run_start"),
                          {"mode": "all_active"})
        self.assertEqual(response.status_code, 302)
        run = AuditRun.objects.get()
        self.assertEqual(run.tests_total, 14)
        self.assertRedirects(response, f"/audit/runs/{run.pk}/")

    def test_run_selected_and_single_guards(self):
        c = self._c(self.auditor)
        ids = [str(self.get_test("T-PROC-01").pk),
               str(self.get_test("T-EXP-01").pk)]
        response = c.post(reverse("audit:run_start"),
                          {"mode": "selected", "test_ids": ids})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AuditRun.objects.get().tests_total, 2)
        # single with two ids → Arabic error message, no run
        response = c.post(reverse("audit:run_start"),
                          {"mode": "single", "test_ids": ids}, follow=True)
        self.assertContains(response, "معرّفًا واحدًا")
        # nothing selected → error
        response = c.post(reverse("audit:run_start"),
                          {"mode": "selected"}, follow=True)
        self.assertContains(response, "لم يتم تحديد")

    def test_run_detail_shows_statuses_and_traceability(self):
        Procurement.objects.create(
            reference_number="PR-H1", date=date(2026, 1, 5),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="بدون عروض",
            amount=D("2500"), status="approved", created_by=self.finance)
        c = self._c(self.auditor)
        c.post(reverse("audit:run_start"), {"mode": "all_active"})
        run = AuditRun.objects.get()
        response = c.get(reverse("audit:run_detail", args=[run.pk]))
        self.assertContains(response, "pass")
        self.assertContains(response, "flagged")
        self.assertContains(response, "لماذا سُجِّل")
        self.assertContains(response, "لقطة المعاملات")
        self.assertContains(response, "Insufficient Quotations")

    def test_create_test_from_ui(self):
        c = self._c(self.auditor)
        response = c.post(reverse("audit:test_create"), {
            "test_code": "T-PROC-09",
            "name": "حد تنافسي أدنى",
            "domain": "procurement",
            "objective": "هدف",
            "rule_text": "قاعدة Synthetic/Training Rule تجريبية",
            "data_source": "procurements",
            "expected_result": "لا شيء",
            "exception_type": "Gap",
            "default_risk": "Medium",
            "auditor_action": "فحص",
            "is_active": "on",
            "synthetic_rule": "on",
            "engine_key": "proc_min_quotes",
            "parameters_json": '{"synthetic_rule": true, "min_quotes": 4, '
                               '"min_amount": 100, "risk_bands": '
                               '{"a3": 10000, "a2": 2000}}',
        })
        self.assertEqual(response.status_code, 302)
        t = AuditTest.objects.get(test_code="T-PROC-09")
        self.assertEqual(t.parameters["min_quotes"], 4)
        self.assertEqual(t.created_by_id, self.auditor.pk)
        # new test runs through same evaluator with own params
        run = engine.start_run([t], self.auditor, mode="single")
        self.assertEqual(run.tests_total, 1)

    def test_create_test_rejects_bad_json_and_unmarked_synthetic(self):
        c = self._c(self.auditor)
        base = {
            "test_code": "T-X-01", "name": "x", "domain": "general",
            "objective": "o", "rule_text": "Synthetic/Training Rule r",
            "data_source": "d", "expected_result": "e",
            "exception_type": "x", "default_risk": "Low",
            "auditor_action": "a", "engine_key": "proc_min_quotes",
        }
        response = c.post(reverse("audit:test_create"),
                          {**base, "parameters_json": "{not json",
                           "synthetic_rule": "on"})
        self.assertContains(response, "JSON غير صالح")
        response = c.post(reverse("audit:test_create"),
                          {**base, "synthetic_rule": "",
                           "parameters_json": '{"synthetic_rule": true}'})
        self.assertContains(response, "قاعدة تدريبية")

    def test_toggle_test_audited(self):
        c = self._c(self.auditor)
        t = self.get_test("T-EXP-06")
        response = c.post(reverse("audit:test_toggle", args=[t.pk]))
        self.assertEqual(response.status_code, 302)
        t.refresh_from_db()
        self.assertFalse(t.is_active)
        self.assertTrue(AuditLog.objects.filter(
            action="entity_updated", entity_type="audit_test",
            entity_id=str(t.pk)).exists())

    def test_exception_status_lifecycle(self):
        Procurement.objects.create(
            reference_number="PR-H2", date=date(2026, 1, 6),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="أخرى بلا عروض",
            amount=D("3000"), status="approved", created_by=self.finance)
        c = self._c(self.auditor)
        c.post(reverse("audit:run_start"), {"mode": "all_active"})
        exc = AuditException.objects.filter(
            test_code="T-PROC-01").order_by("-amount").first()
        self.assertIsNotNone(exc)
        # list page + filters
        response = c.get(reverse("audit:exceptions_list"))
        self.assertContains(response, "لماذا سُجِّل")
        response = c.get(reverse("audit:exceptions_list"),
                         {"test_code": "T-PROC-01"})
        self.assertContains(response, "Insufficient")
        # acknowledge → resolved → open
        response = c.post(reverse("audit:exception_update", args=[exc.pk]),
                          {"status": "acknowledged", "status_note": "دراسة"})
        self.assertEqual(response.status_code, 302)
        exc.refresh_from_db()
        self.assertEqual(exc.status, "acknowledged")
        self.assertEqual(exc.handled_by_id, self.auditor.pk)
        c.post(reverse("audit:exception_update", args=[exc.pk]),
               {"status": "resolved", "status_note": "مغلق"})
        exc.refresh_from_db()
        self.assertEqual(exc.status, "resolved")
        self.assertTrue(AuditLog.objects.filter(
            action="entity_updated", entity_type="audit_exception",
            entity_id=str(exc.pk)).exists())
        # finance cannot manage exceptions
        cf = self._c(self.finance)
        self.assertEqual(
            cf.post(reverse("audit:exception_update", args=[exc.pk]),
                    {"status": "open"}).status_code, 403)

    def test_runs_list_page(self):
        self.run_one("T-PROC-04")
        response = self._c(self.auditor).get(reverse("audit:runs_list"))
        self.assertContains(response, "AR-2026-00001")


# ================================================================ catalog
class CatalogInvariantTests(TestCase):
    def test_catalog_stays_30_and_audit_rules_mapped(self):
        self.assertEqual(len(PERMISSIONS), 30)
        expect = {
            "audit:tests_list": "audit.view",
            "audit:runs_list": "audit.view",
            "audit:run_detail": "audit.view",
            "audit:test_create": "audit.rules.manage",
            "audit:test_edit": "audit.rules.manage",
            "audit:test_toggle": "audit.rules.manage",
            "audit:run_start": "audit.run",
            "audit:exceptions_list": "exceptions.view",
            "audit:exception_update": "exceptions.manage",
        }
        for name, code in expect.items():
            self.assertEqual(URL_PERMISSIONS[name], code)
        self.assertIn("audit.view", ALL_CODES)
        self.assertIn("audit.run", ALL_CODES)
        self.assertIn("audit.rules.manage", ALL_CODES)


# ================================================================ PHASE 10
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ExceptionEvidenceTests(BaseFixture):
    def test_engine_snapshots_auditor_action(self):
        Procurement.objects.create(
            reference_number="PR-EV1", date=date(2026, 1, 5),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="بلا عروض",
            amount=D("3000"), status="approved", created_by=self.finance)
        run = self.run_one("T-PROC-01")
        exc = run.exceptions.get()
        self.assertEqual(exc.auditor_action,
                         self.get_test("T-PROC-01").auditor_action)
        self.assertTrue(exc.auditor_action)

    def test_evidence_upload_view_and_rbac(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        Procurement.objects.create(
            reference_number="PR-EV2", date=date(2026, 1, 6),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="بلا عروض 2",
            amount=D("4000"), status="approved", created_by=self.finance)
        run = self.run_one("T-PROC-01")
        exc = run.exceptions.get()

        ca = Client(); ca.force_login(self.auditor)
        # upload
        response = ca.post(
            reverse("audit:evidence_upload", args=[exc.pk]),
            {"evidence": SimpleUploadedFile("evidence.pdf", b"%PDF-1.4 ev")})
        self.assertEqual(response.status_code, 302)
        exc.refresh_from_db()
        self.assertTrue(exc.evidence)
        # view → 200 + audit action
        response = ca.get(reverse("audit:evidence_view", args=[exc.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 ev")
        self.assertTrue(AuditLog.objects.filter(
            action="exception_evidence_viewed",
            entity_id=str(exc.pk)).exists())
        # finance: no exceptions.manage / view
        cf = Client(); cf.force_login(self.finance)
        self.assertEqual(
            cf.post(reverse("audit:evidence_upload", args=[exc.pk]),
                    {"evidence": SimpleUploadedFile("x.pdf", b"x")}
                    ).status_code, 403)
        # oversized rejected (Arabic)
        big = SimpleUploadedFile("big.pdf",
                                 b"x" * (11 * 1024 * 1024))
        response = ca.post(reverse("audit:evidence_upload", args=[exc.pk]),
                           {"evidence": big})
        # rendered redirect w/ error message (no file saved) — job stays 302
        self.assertEqual(response.status_code, 302)

    def test_exception_detail_shows_chain(self):
        p = Procurement.objects.create(
            reference_number="PR-EV3", date=date(2026, 1, 7),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="تتبّع",
            amount=D("2600"), status="approved", created_by=self.finance)
        run = self.run_one("T-PROC-01")
        exc = run.exceptions.get()
        ca = Client(); ca.force_login(self.auditor)
        response = ca.get(reverse("audit:exception_detail", args=[exc.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "سلسلة التتبّع")
        self.assertContains(response, f"/procurement/{p.pk}/")     # → source
        self.assertContains(response, "T-PROC-01")                 # → test
        self.assertContains(response, "Auditor Action")
        self.assertContains(response, "لا AI/ML")                  # risk note
        self.assertContains(response, "إنشاء Finding")            # → finding
        # anon redirected / finance denied
        self.assertEqual(
            self.client.get(
                reverse("audit:exception_detail", args=[exc.pk])
            ).status_code, 302)
        cf = Client(); cf.force_login(self.finance)
        self.assertEqual(
            cf.get(reverse("audit:exception_detail", args=[exc.pk])
                   ).status_code, 403)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class FindingTests(BaseFixture):
    def _make_exception(self, ref, amount):
        Procurement.objects.create(
            reference_number=ref, date=date(2026, 1, 5),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="اختبار", amount=D(str(amount)),
            status="approved", created_by=self.finance)
        return None

    def test_finding_auto_code_sequence(self):
        from apps.audit_register.models import AuditFinding
        from apps.audit_register import services as eng
        f1 = AuditFinding.objects.create(
            finding_code=eng.next_finding_code(), title="أولى",
            criteria="c", condition="d", impact="i",
            recommendation="r")
        f2 = AuditFinding.objects.create(
            finding_code=eng.next_finding_code(), title="ثانية",
            criteria="c", condition="d", impact="i",
            recommendation="r")
        self.assertEqual(f1.finding_code, "F-2026-00001")
        self.assertEqual(f2.finding_code, "F-2026-00002")

    def test_cause_only_when_supported(self):
        from apps.audit_register.forms import FindingForm
        base = {"title": "t", "criteria": "c", "condition": "d",
                "impact": "i", "recommendation": "r",
                "risk_level": "Medium", "status": "open"}
        # cause without support → Arabic rejection
        form = FindingForm(data={**base, "cause": "سبب مفترض"})
        self.assertFalse(form.is_valid())
        self.assertIn("لا يُكتب إلا مع دليل", str(form.errors["__all__"]))
        # cause with support → valid
        form = FindingForm(data={**base, "cause": "سبب مثبت",
                                 "cause_supported": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        # no cause → valid, supported forced off
        form = FindingForm(data=base)
        self.assertTrue(form.is_valid(), form.errors)

    def test_finding_http_flow_prefill_link_status(self):
        # two exceptions: High (≥10k, no quotes) + Low (missing PO <2k)
        p1 = Procurement.objects.create(
            reference_number="PR-F1", date=date(2026, 1, 5),
            department=self.dept_ops, supplier=self.sup1,
            account=self.acc5102, description="كبير بلا عروض",
            purchase_order="PO-PR-F1", amount=D("15000"),
            status="approved", created_by=self.finance)
        Procurement.objects.create(
            reference_number="PR-F2", date=date(2026, 1, 6),
            department=self.dept_adm, supplier=self.sup1,
            account=self.acc5310, description="صغير بلا PO",
            amount=D("600"), status="draft", created_by=self.finance)
        run = engine.start_run(
            AuditTest.objects.filter(is_active=True), self.auditor,
            mode="all_active")
        high = run.exceptions.filter(test_code="T-PROC-01").first()
        low = run.exceptions.filter(test_code="T-PROC-02").first()
        self.assertEqual(high.risk_level, "High")
        self.assertEqual(low.risk_level, "Low")

        ca = Client(); ca.force_login(self.auditor)
        # GET prefilled from exception (worst risk = High)
        response = ca.get(reverse("audit:finding_create"),
                          {"exception": high.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مُعبّأة مسبقًا")
        # POST create linked to BOTH exceptions
        response = ca.post(reverse("audit:finding_create"), {
            "exception": str(high.pk),
            "title": "ضعف منافسة في المشتريات الكبرى",
            "criteria": "سياسة P1 (تدريبية): 3 عروض ≥ 1000",
            "condition": "سجلان بلا عروض كافية",
            "impact": "تعرّض لسعر غير منافس — أثر مالي مباشر محتمل",
            "cause": "", "risk_level": "High",
            "recommendation": "تفعيل منافسة إلزامية فوق العتبة",
            "management_action": "", "status": "open", "status_note": "",
        })
        self.assertEqual(response.status_code, 302)
        from apps.audit_register.models import AuditFinding
        finding = AuditFinding.objects.get()
        self.assertEqual(finding.finding_code, "F-2026-00001")
        self.assertEqual(finding.exceptions.count(), 1)
        self.assertEqual(finding.created_by_id, self.auditor.pk)
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="audit_finding",
            entity_id=str(finding.pk)).exists())
        # chain: finding detail → exceptions → source → test
        response = ca.get(reverse("audit:finding_detail",
                                  args=[finding.pk]))
        self.assertContains(response, f"/procurement/{p1.pk}/")
        self.assertContains(response, "/audit/tests/")
        # edit: management action + status
        response = ca.post(reverse("audit:finding_edit", args=[finding.pk]), {
            "title": finding.title, "criteria": finding.criteria,
            "condition": finding.condition, "impact": finding.impact,
            "cause": "", "cause_supported": "", "risk_level": "High",
            "recommendation": finding.recommendation,
            "management_action": "رُفعت لجنة المشتريات — تعزيز المنافسة",
            "status": "in_progress", "status_note": "بدأت المعالجة",
        })
        self.assertEqual(response.status_code, 302)
        finding.refresh_from_db()
        self.assertEqual(finding.status, "in_progress")
        self.assertTrue(finding.management_action)
        self.assertTrue(AuditLog.objects.filter(
            action="entity_updated", entity_type="audit_finding",
            entity_id=str(finding.pk)).exists())

    def test_findings_list_filters_and_rbac(self):
        from apps.audit_register.models import AuditFinding
        AuditFinding.objects.create(
            finding_code="F-2026-00100", title="قديمة",
            criteria="c", condition="d", impact="i", recommendation="r",
            status="closed", risk_level="Low")
        ca = Client(); ca.force_login(self.auditor)
        response = ca.get(reverse("audit:findings_list"))
        self.assertContains(response, "F-2026-00100")
        response = ca.get(reverse("audit:findings_list"),
                          {"status": "closed", "risk": "Low"})
        self.assertContains(response, "F-2026-00100")
        # management: findings.view yes — manage no
        cm = Client(); cm.force_login(self.mgmt)
        self.assertEqual(
            cm.get(reverse("audit:findings_list")).status_code, 200)
        self.assertEqual(
            cm.post(reverse("audit:finding_create"), {}).status_code, 403)
        # finance: no findings access
        cf = Client(); cf.force_login(self.finance)
        self.assertEqual(
            cf.get(reverse("audit:findings_list")).status_code, 403)
        # anon
        self.assertEqual(
            self.client.get(reverse("audit:findings_list")).status_code, 302)


class CycleHubTests(BaseFixture):
    def test_hub_counts_and_links(self):
        ca = Client(); ca.force_login(self.auditor)
        response = ca.get(reverse("audit:cycle_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دورة المعالجة الرقابية")
        self.assertContains(response, "Audit Test → Exception")
        self.assertContains(response, "لا AI/ML")
        self.assertContains(response, "/audit/exceptions/")
        self.assertContains(response, "/audit/findings/")
        # management: no audit.view → 403 (hub is audit cycle control)
        cm = Client(); cm.force_login(self.mgmt)
        self.assertEqual(
            cm.get(reverse("audit:cycle_hub")).status_code, 403)
        # finance 403, anon redirect
        cf = Client(); cf.force_login(self.finance)
        self.assertEqual(
            cf.get(reverse("audit:cycle_hub")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("audit:cycle_hub")).status_code, 302)


class CatalogPhase10Tests(TestCase):
    def test_catalog_30_and_new_rules(self):
        self.assertEqual(len(PERMISSIONS), 30)
        expect = {
            "audit:cycle_hub": "audit.view",
            "audit:exception_detail": "exceptions.view",
            "audit:evidence_view": "exceptions.view",
            "audit:evidence_upload": "exceptions.manage",
            "audit:findings_list": "findings.view",
            "audit:finding_detail": "findings.view",
            "audit:finding_create": "findings.manage",
            "audit:finding_edit": "findings.manage",
        }
        for name, code in expect.items():
            self.assertEqual(URL_PERMISSIONS[name], code)
        self.assertEqual(
            len([k for k in URL_PERMISSIONS if k.startswith("audit:")]), 17)
