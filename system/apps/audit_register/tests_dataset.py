"""PHASE 13 — Synthetic Training Dataset + Ground Truth + automated proofs.

إثبات آلي (لا يكفي أن تعمل الصفحة):
  1.  المُحمّل (loader) يبني مجموعة تدريبية اصطناعية متوازنة ويُعيد تشغيله
      بلا تضاعف (idempotent).
  2.  Ground Truth مُعلن مسبقًا في `datasets.training.EXPECTED_EXCEPTIONS`
      ويُقارن بتساويٍ تام (للوجهين) مع مخرجات محرك الاختبارات الرقابية:
      استثناء ناقق أو علم زائد = فشل.
  3.  تغطية الأوامر التسعة: مصادقة · صلاحيات · CRUD · استيراد · حسابات ·
      قواعد التدقيق · استثناءات · مخاطر · تقارير · استعلامات اللوحة.

Synthetic/Training only — لا بيانات حقيقية ولا ارتباط بأي جهة (SYNTHETIC).
"""
from __future__ import annotations

import tempfile
from collections import Counter
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import (
    ALL_CODES, PERMISSIONS, ROLES, URL_PERMISSIONS, user_permission_codes,
)
from apps.audit_register import services as engine
from apps.audit_register.models import (
    AuditException, AuditRun, AuditTest, AuditTestResult,
)
from apps.budget.models import BudgetLine, BudgetVersion
from apps.expenses.models import Expense
from apps.governance.models import AuditLog
from apps.imports import services as import_svc
from apps.imports.models import ImportJob
from apps.procurement.models import Procurement, Quotation
from apps.reference.models import (
    Account, Department, ExpenseCategory, MonthlyPeriod, Supplier,
)
from datasets.training import (
    BUDGET_LINES, BUDGET_NAME, DS_PASSWORD, EXPECTED_EXCEPTIONS,
    EXPECTED_PER_TEST, EXPECTED_TOTAL, EXPENSES, MUST_NOT_FLAG,
    OOB_AMOUNT, OOB_COUNT, RISK_COUNTS, RISK_SPOT_CHECKS,
    SYNTHETIC_DECLARATION, TARGETED_NEGATIVES, TOTAL_ACTUAL, TOTAL_BUDGET,
    UTILIZATION_FMT, VARIANCE, load_training_dataset,
)

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp(prefix="p13_media_")

IMPORT_CSV = (
    "Date,Department,Account,Supplier,Description,Amount,Invoice,Currency,"
    "Payment Method\n"
    "2026-02-05,D-LOG,5601,SUP-TRN-A,مصروف مستورد تجريبي أ,320.50,"
    "IMP-INV-1,USD,transfer\n"
    "2026-02-06,D-LOG,5601,SUP-TRN-A,مصروف مستورد تجريبي ب,150,"
    "IMP-INV-2,USD,transfer\n"
    "2026-02-07,D-LOG,5601,SUP-TRN-A,مبلغ غير صالح,-10,"
    "IMP-INV-3,USD,transfer\n"
    "2026-02-05,D-LOG,5601,SUP-TRN-A,مصروف مستورد تجريبي أ,320.50,"
    "IMP-INV-1,USD,transfer\n"
)


# ---------------------------------------------------------------- helpers
def build_key(exc, dept_codes, acc_codes) -> tuple:
    """(test_code, exception_type, subject) — the ground-truth key format."""
    ref = exc.source_ref or {}
    if exc.source_type == "expense":
        subject = f"expense:{ref.get('expense_number')}"
    elif exc.source_type == "procurement":
        subject = f"proc:{ref.get('reference_number')}"
    elif exc.source_type == "budget_combination":
        dept = dept_codes[ref["department_id"]]
        acc = acc_codes[ref["account_id"]]
        if "month" in ref:
            subject = f"combo:{dept}:{acc}:m{int(ref['month']):02d}"
        else:
            subject = f"combo:{dept}:{acc}"
    else:
        subject = f"{exc.source_type}:{exc.source_id}"
    return (exc.test_code, exc.exception_type, subject)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DatasetBase(TestCase):
    """Loads the synthetic dataset once per test class + shared helpers."""

    @classmethod
    def setUpTestData(cls):
        cls.stats = load_training_dataset()
        cls.ds_admin = User.objects.get(username="ds_admin")
        cls.ds_auditor = User.objects.get(username="ds_auditor")
        cls.ds_finance = User.objects.get(username="ds_finance")
        cls.ds_mgmt = User.objects.get(username="ds_mgmt")

    # -------------------------------------------------- shared utilities
    @classmethod
    def run_all_tests(cls, user=None):
        tests = list(
            AuditTest.objects.filter(is_active=True).order_by("test_code"))
        return engine.start_run(
            tests, user or cls.ds_auditor, mode="all_active")

    @classmethod
    def keys_of(cls, run):
        dept_codes = {d.pk: d.code for d in Department.objects.all()}
        acc_codes = {a.pk: a.code for a in Account.objects.all()}
        return {build_key(e, dept_codes, acc_codes)
                for e in AuditException.objects.filter(run=run)}

    @classmethod
    def exception_for(cls, run, key):
        dept_codes = {d.pk: d.code for d in Department.objects.all()}
        acc_codes = {a.pk: a.code for a in Account.objects.all()}
        for e in AuditException.objects.filter(run=run):
            if build_key(e, dept_codes, acc_codes) == key:
                return e
        return None

    def period_pk(self, month):
        return MonthlyPeriod.objects.get(
            fiscal_year__code="FY2026", month=month).pk


# ============================================================ 1) loader
class DatasetLoaderTests(DatasetBase):
    def test_synthetic_declaration_present(self):
        self.assertIn("SYNTHETIC", SYNTHETIC_DECLARATION)
        self.assertIn("اصطناعية", SYNTHETIC_DECLARATION)
        self.assertEqual(self.stats["declaration"], SYNTHETIC_DECLARATION)

    def test_dimension_counts(self):
        self.assertEqual(Department.objects.count(), 4)
        self.assertEqual(ExpenseCategory.objects.count(), 4)
        self.assertEqual(Account.objects.count(), 5)
        self.assertEqual(Supplier.objects.count(), 4)
        self.assertEqual(Supplier.objects.filter(is_active=False).count(), 1)
        self.assertEqual(MonthlyPeriod.objects.count(), 12)
        self.assertEqual(User.objects.filter(
            username__startswith="ds_").count(), 4)

    def test_users_bound_to_approved_roles(self):
        expected = {
            "ds_admin": "admin", "ds_auditor": "auditor",
            "ds_finance": "finance", "ds_mgmt": "management",
        }
        for username, role in expected.items():
            self.assertTrue(UserRole.objects.filter(
                user__username=username, role__code=role).exists(),
                f"{username} ↔ {role}")

    def test_budget_lines_and_hand_calculation(self):
        version = BudgetVersion.objects.get(status="approved")
        lines = BudgetLine.objects.filter(version=version)
        self.assertEqual(lines.count(), 5)
        # hand calculation from the declared constants …
        declared = sum(monthly * 12
                       for _, _, monthly in BUDGET_LINES)
        self.assertEqual(declared, TOTAL_BUDGET)
        self.assertEqual(TOTAL_BUDGET, D("69000"))
        # … and from the database (derived annual_amount per line)
        self.assertEqual(
            sum(lines.values_list("annual_amount", flat=True)),
            TOTAL_BUDGET)

    def test_expense_dataset_shape_and_totals(self):
        self.assertEqual(Expense.objects.count(), 43)
        qs = Expense.objects.all()
        self.assertFalse(qs.exclude(currency="USD").exists())
        # three independent totals: declared literals vs rows vs database
        self.assertEqual(sum(r["amount"] for r in EXPENSES), TOTAL_ACTUAL)
        self.assertEqual(TOTAL_ACTUAL, D("123190"))
        self.assertEqual(qs.aggregate(s=Sum("amount"))["s"], TOTAL_ACTUAL)
        # rule-critical shapes: exactly one of each anomaly class
        self.assertEqual(
            list(qs.filter(approval_reference="").values_list(
                "expense_number", flat=True)), ["E-UNAP"])
        self.assertEqual(
            list(qs.filter(attachment="").values_list(
                "expense_number", flat=True)), ["E-DOC1"])
        self.assertEqual(
            list(qs.filter(payment_method="cash").values_list(
                "expense_number", flat=True)), ["E-CASH"])

    def test_out_of_budget_totals_hand_checked(self):
        budget_keys = set(BudgetLine.objects.filter(
            version__status="approved"
        ).values_list("department_id", "account_id"))
        oob = [e for e in Expense.objects.all()
               if (e.department_id, e.account_id) not in budget_keys]
        self.assertEqual(len(oob), OOB_COUNT)
        self.assertEqual(len(oob), 8)
        self.assertEqual(sum(e.amount for e in oob), OOB_AMOUNT)
        self.assertEqual(OOB_AMOUNT, D("18550"))

    def test_procurement_dataset_shape(self):
        self.assertEqual(Procurement.objects.count(), 9)
        self.assertEqual(Quotation.objects.count(), 18)
        self.assertEqual(Procurement.objects.filter(
            status="cancelled").count(), 1)
        p5 = Procurement.objects.get(reference_number="P-TRN-05")
        self.assertFalse(p5.supplier.is_active)   # loaded on purpose

    def test_loader_is_idempotent(self):
        before = (Expense.objects.count(), Procurement.objects.count(),
                  Quotation.objects.count(), BudgetLine.objects.count(),
                  MonthlyPeriod.objects.count())
        call_command("load_training_dataset", verbosity=0)
        call_command("load_training_dataset", verbosity=0)
        after = (Expense.objects.count(), Procurement.objects.count(),
                 Quotation.objects.count(), BudgetLine.objects.count(),
                 MonthlyPeriod.objects.count())
        self.assertEqual(before, after)
        self.assertEqual(before[:2], (43, 9))


# ============================================================ 2) auth
class AuthenticationTests(DatasetBase):
    def test_login_success_is_logged(self):
        resp = self.client.post(reverse("accounts:login"), {
            "username": "ds_finance", "password": DS_PASSWORD})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(AuditLog.objects.filter(
            action="login", actor=self.ds_finance).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]),
                         self.ds_finance.pk)

    def test_login_failure_is_logged_without_actor(self):
        resp = self.client.post(reverse("accounts:login"), {
            "username": "ds_finance", "password": "wrong-password"})
        self.assertEqual(resp.status_code, 200)          # form re-rendered
        self.assertTrue(AuditLog.objects.filter(
            action="login_failed", actor=None).exists())

    def test_logout_is_logged(self):
        self.client.force_login(self.ds_finance)
        resp = self.client.post(reverse("accounts:logout"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(AuditLog.objects.filter(
            action="logout", entity_type="user",
            entity_id=self.ds_finance.pk).exists())

    def test_effective_permission_sets_per_role(self):
        admin = user_permission_codes(self.ds_admin)
        auditor = user_permission_codes(self.ds_auditor)
        finance = user_permission_codes(self.ds_finance)
        mgmt = user_permission_codes(self.ds_mgmt)
        self.assertEqual(admin, ALL_CODES)
        self.assertEqual(auditor, set(ROLES["auditor"]["permissions"]))
        self.assertEqual(finance, set(ROLES["finance"]["permissions"]))
        self.assertEqual(mgmt, set(ROLES["management"]["permissions"]))
        # behavioural spot-checks
        self.assertIn("audit.run", auditor)
        self.assertNotIn("expenses.edit", auditor)
        self.assertIn("expenses.edit", finance)
        self.assertNotIn("audit.view", finance)
        self.assertEqual(len(mgmt), 5)
        self.assertTrue(mgmt <= ALL_CODES)


# ============================================================ 3) permissions
class PermissionMatrixTests(DatasetBase):
    def test_catalog_stays_30_and_gates_reference_it(self):
        self.assertEqual(len(PERMISSIONS), 30)
        self.assertEqual(len(ALL_CODES), 30)
        for view_name, code in URL_PERMISSIONS.items():
            self.assertIn(code, ALL_CODES, view_name)

    def test_page_level_matrix(self):
        cases = [
            # (user, url name/args, expected status)
            (None, "dashboard:index", [], 302),        # anon → login
            (self.ds_mgmt, "dashboard:index", [], 200),
            (self.ds_mgmt, "expenses:list", [], 403),
            (self.ds_finance, "expenses:create", [], 200),
            (self.ds_mgmt, "expenses:create", [], 403),
            (self.ds_mgmt, "audit:tests_list", [], 403),
            (self.ds_finance, "audit:tests_list", [], 403),
            (self.ds_auditor, "audit:tests_list", [], 200),
            (self.ds_mgmt, "governance:audit_trail", [], 403),
            (self.ds_auditor, "governance:audit_trail", [], 200),
            (self.ds_mgmt, "reports:list", [], 200),
            (self.ds_finance, "reference:department_create", [], 403),
        ]
        for user, name, args, status in cases:
            if user is None:
                self.client.logout()
            else:
                self.client.force_login(user)
            resp = self.client.get(reverse(name, args=args))
            self.assertEqual(resp.status_code, status,
                             f"{user} × {name} → {resp.status_code}")

    def test_export_gate_reports_generate_only(self):
        self.client.force_login(self.ds_mgmt)
        resp = self.client.get(
            reverse("reports:export", args=["exception-register", "csv"]))
        self.assertEqual(resp.status_code, 403)
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("reports:export", args=["exception-register", "csv"]))
        # no run yet in this test → report still renders (0 rows)
        self.assertEqual(resp.status_code, 200)

    def test_action_level_run_start_gate(self):
        for user in (self.ds_mgmt, self.ds_finance):
            self.client.force_login(user)
            resp = self.client.post(reverse("audit:run_start"),
                                    {"mode": "all_active"})
            self.assertEqual(resp.status_code, 403, user.username)
        self.assertEqual(AuditRun.objects.count(), 0)
        self.client.force_login(self.ds_auditor)
        resp = self.client.post(reverse("audit:run_start"),
                                {"mode": "all_active"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AuditRun.objects.count(), 1)


# ============================================================ 4) CRUD
class CrudTests(DatasetBase):
    def _create_payload(self, **overrides):
        payload = {
            "expense_number": "E-TRN-NEW-01",
            "expense_date": "2026-02-16",
            "period": str(self.period_pk(2)),
            "department": str(Department.objects.get(code="D-LOG").pk),
            "account": str(Account.objects.get(code="5601").pk),
            "expense_category": "",
            "supplier": "",
            "description": "مصروف تدريبي يُنشأ من اختبار CRUD",
            "amount": "123.45",
            "currency": "USD",
            "payment_method": "transfer",
            "payment_reference": "",
            "invoice_reference": "INV-CRUD-1",
            "attachment": "",
            "approval_reference": "APV-CRUD-1",
        }
        payload.update(overrides)
        return payload

    def test_create_writes_row_and_audit_log(self):
        self.client.force_login(self.ds_finance)
        upload = SimpleUploadedFile(
            "crud.pdf", b"%PDF-1.4 crud", content_type="application/pdf")
        resp = self.client.post(
            reverse("expenses:create"),
            {**self._create_payload(), "attachment": upload})
        self.assertEqual(resp.status_code, 302)
        e = Expense.objects.get(expense_number="E-TRN-NEW-01")
        self.assertEqual(e.amount, D("123.45"))
        self.assertEqual(e.created_by, self.ds_finance)
        self.assertEqual(e.approval_reference, "APV-CRUD-1")
        self.assertTrue(e.attachment)
        log = AuditLog.objects.filter(
            action="entity_created", entity_type="expense",
            entity_id=e.pk).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.ds_finance)
        detail = self.client.get(
            reverse("expenses:detail", args=[e.pk]))
        self.assertEqual(detail.status_code, 200)

    def test_create_rejects_duplicate_invoice(self):
        self.client.force_login(self.ds_finance)
        payload = self._create_payload(
            expense_number="E-TRN-NEW-02",
            expense_date="2026-04-10",
            period=str(self.period_pk(4)),
            department=str(Department.objects.get(code="D-QA").pk),
            supplier=str(Supplier.objects.get(code="SUP-TRN-B").pk),
            amount="1250",
            invoice_reference="TRN-INV-B410",
        )
        resp = self.client.post(reverse("expenses:create"), payload)
        self.assertEqual(resp.status_code, 200)      # form errors, no insert
        self.assertFalse(Expense.objects.filter(
            expense_number="E-TRN-NEW-02").exists())
        self.assertEqual(Expense.objects.count(), 43)
        self.assertContains(resp, "مكرر")

    def test_create_requires_amount(self):
        self.client.force_login(self.ds_finance)
        resp = self.client.post(
            reverse("expenses:create"), self._create_payload(amount=""))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Expense.objects.count(), 43)

    def test_edit_updates_amount_and_logs_before_after(self):
        self.client.force_login(self.ds_finance)
        e = Expense.objects.get(expense_number="E-QSU-01")
        payload = self._create_payload(
            expense_number="E-QSU-01",
            expense_date="2026-02-11",
            department=str(Department.objects.get(code="D-QA").pk),
            supplier="",
            description="مستلزمات مكتبية للجودة",
            amount="777",
            invoice_reference="INV-Q01",
            approval_reference="APV",
        )
        resp = self.client.post(
            reverse("expenses:edit", args=[e.pk]), payload)
        self.assertEqual(resp.status_code, 302)
        e.refresh_from_db()
        self.assertEqual(e.amount, D("777"))
        self.assertEqual(e.updated_by, self.ds_finance)
        log = AuditLog.objects.filter(
            action="entity_updated", entity_type="expense",
            entity_id=e.pk).first()
        self.assertIsNotNone(log)
        self.assertIn("amount", log.diff)
        self.assertEqual(float(log.diff["amount"]["before"]), 700.0)
        self.assertEqual(float(log.diff["amount"]["after"]), 777.0)

    def test_anonymous_cannot_create(self):
        resp = self.client.post(
            reverse("expenses:create"), self._create_payload())
        self.assertEqual(resp.status_code, 302)      # → login


# ============================================================ 5) imports
class ImportTests(DatasetBase):
    def test_csv_valid_invalid_duplicate_counts(self):
        self.client.force_login(self.ds_finance)
        upload = SimpleUploadedFile(
            "training_import.csv", IMPORT_CSV.encode("utf-8"),
            content_type="text/csv")
        resp = self.client.post(reverse("imports:new"), {
            "target": ImportJob.TARGET_EXPENSES, "source_file": upload})
        self.assertEqual(resp.status_code, 302)
        job = ImportJob.objects.get()
        self.assertEqual(job.status, ImportJob.STATUS_EXTRACTED)
        self.assertEqual(len(job.rows), 4)
        # required columns auto-mapped from the dataset-shaped headers
        for field in ("expense_date", "department", "account",
                      "description", "amount"):
            self.assertTrue(job.column_map.get(field), field)

        summary = import_svc.validate_job(job, self.ds_finance)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.STATUS_VALIDATED)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["valid"], 2)
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(summary["duplicate"], 1)
        messages = " ".join(e["message"] for e in summary["error_list"])
        self.assertIn("المبلغ", messages)            # −10 rejected
        self.assertIn("مكرر", messages)              # in-file duplicate

        imported = import_svc.run_import(job, self.ds_finance)
        self.assertEqual(imported, 2)
        self.assertEqual(Expense.objects.count(), 45)   # 43 + 2 valid
        self.assertTrue(AuditLog.objects.filter(
            action="data_imported", entity_type="import_job",
            entity_id=job.pk).exists())

    def test_import_requires_permission(self):
        self.client.force_login(self.ds_mgmt)        # no imports.* codes
        upload = SimpleUploadedFile(
            "x.csv", IMPORT_CSV.encode("utf-8"), content_type="text/csv")
        resp = self.client.post(reverse("imports:new"), {
            "target": ImportJob.TARGET_EXPENSES, "source_file": upload})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(ImportJob.objects.count(), 0)


# ============================================================ 6) calculations
class CalculationTests(DatasetBase):
    """Hand calculations vs ORM vs live dashboard/report figures."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.audit_run = cls.run_all_tests()

    def test_budget_total_hand_math(self):
        version = BudgetVersion.objects.get(status="approved")
        orm_total = BudgetLine.objects.filter(
            version=version).aggregate(s=Sum("annual_amount"))["s"]
        hand = (D("2000") + D("1000") + D("1500") + D("750")
                + D("500")) * 12
        self.assertEqual(hand, D("69000"))
        self.assertEqual(hand, TOTAL_BUDGET)
        self.assertEqual(orm_total, TOTAL_BUDGET)

    def test_actual_total_hand_math(self):
        hand = sum(r["amount"] for r in EXPENSES)
        orm = Expense.objects.aggregate(s=Sum("amount"))["s"]
        self.assertEqual(hand, D("123190"))
        self.assertEqual(hand, TOTAL_ACTUAL)
        self.assertEqual(orm, TOTAL_ACTUAL)
        # variance sign convention: Budget − Actual (negative = over-spent)
        self.assertEqual(TOTAL_BUDGET - TOTAL_ACTUAL, VARIANCE)
        self.assertEqual(VARIANCE, D("-54190"))

    def test_dashboard_kpis_match_hand_calculations(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resp.status_code, 200)
        kpis = resp.context["kpis"]
        fmt = resp.context["kpis_fmt"]
        self.assertEqual(kpis["effective_budget"], TOTAL_BUDGET)
        self.assertEqual(kpis["actual"], TOTAL_ACTUAL)
        self.assertEqual(kpis["variance"], VARIANCE)
        self.assertEqual(fmt["utilization"], UTILIZATION_FMT)
        self.assertEqual(fmt["utilization"], "178.5")
        self.assertEqual(kpis["oob_count"], OOB_COUNT)
        self.assertEqual(kpis["oob_amount"], OOB_AMOUNT)
        # engine-derived KPIs (run executed in setUpTestData)
        self.assertEqual(kpis["exceptions"], EXPECTED_TOTAL)
        self.assertEqual(kpis["high_risk"], RISK_COUNTS["High"])
        self.assertEqual(kpis["proc_exceptions"], 8)

    def test_budget_vs_actual_report_summary(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("reports:detail", args=["budget-vs-actual"]))
        self.assertEqual(resp.status_code, 200)
        summary = {s["label"]: s["value"] for s in resp.context["summary"]}
        self.assertEqual(summary["Effective Budget"], "69,000.00")
        self.assertEqual(summary["Actual Expenses"], "123,190.00")
        self.assertEqual(summary["Variance"], "-54,190.00")
        self.assertEqual(resp.context["row_count"], 12)  # 5 + 7 combos


# ============================================================ 7) ground truth
class GroundTruthTests(DatasetBase):
    """THE proof: engine output == pre-declared ground truth, both ways."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.audit_run = cls.run_all_tests()

    def test_engine_completed_all_14_without_failure(self):
        self.assertEqual(self.audit_run.status, AuditRun.STATUS_COMPLETED)
        self.assertEqual(self.audit_run.tests_total, 14)
        self.assertEqual(self.audit_run.tests_fail, 0)
        self.assertEqual(self.audit_run.tests_pass, 0)
        self.assertEqual(self.audit_run.tests_flagged, 14)
        results = AuditTestResult.objects.filter(run=self.audit_run)
        self.assertEqual(results.count(), 14)
        self.assertFalse(results.exclude(status="flagged").exists())

    def test_total_exceptions_equals_declared_total(self):
        self.assertEqual(AuditException.objects.filter(
            run=self.audit_run).count(), EXPECTED_TOTAL)
        self.assertEqual(self.audit_run.exceptions_total, EXPECTED_TOTAL)
        self.assertEqual(EXPECTED_TOTAL, 28)
        self.assertEqual(len(EXPECTED_EXCEPTIONS), 28)

    def test_exact_ground_truth_set_both_directions(self):
        actual = self.keys_of(self.audit_run)
        missing = EXPECTED_EXCEPTIONS - actual
        unexpected = actual - EXPECTED_EXCEPTIONS
        self.assertEqual(
            actual, EXPECTED_EXCEPTIONS,
            f"\nmissing (declared but not detected): {sorted(missing)}"
            f"\nUNEXPECTED (detected but not declared): {sorted(unexpected)}")

    def test_counts_per_test_code(self):
        counts = Counter(AuditException.objects.filter(
            run=self.audit_run).values_list("test_code", flat=True))
        self.assertEqual(dict(counts), EXPECTED_PER_TEST)

    def test_records_checked_invariants(self):
        checked = {
            r.test.test_code: r.records_checked
            for r in AuditTestResult.objects.filter(run=self.audit_run)
        }
        self.assertEqual(checked["T-BUD-01"], 5)   # 5 approved budget lines
        self.assertEqual(checked["T-BUD-02"], 43)  # all dataset expenses
        self.assertEqual(checked["T-PROC-01"], 8)  # cancelled excluded
        self.assertEqual(checked["T-PROC-03"], 9)  # cancelled included
        self.assertEqual(checked["T-EXP-01"], 43)

    def test_must_not_flag_subjects(self):
        subjects = {key[2] for key in self.keys_of(self.audit_run)}
        leaked = [s for s in MUST_NOT_FLAG if s in subjects]
        self.assertEqual(leaked, [], f"clean controls flagged: {leaked}")

    def test_targeted_negatives_absent(self):
        actual_pairs = {(t, s) for (t, _ty, s) in
                        self.keys_of(self.audit_run)}
        for key in TARGETED_NEGATIVES:
            self.assertNotIn(key, actual_pairs,
                             f"negative case flagged: {key}")
        # E-CASH: Large Cash YES, Unapproved NO (approved + cash)
        cash_types = {
            e.exception_type for e in AuditException.objects.filter(
                run=self.audit_run, test_code="T-EXP-02",
                source_ref__expense_number="E-CASH")
        }
        self.assertEqual(cash_types, {"Large Cash Payment"})

    def test_hand_computed_finding_amounts(self):
        dept_codes = {d.pk: d.code for d in Department.objects.all()}
        acc_codes = {a.pk: a.code for a in Account.objects.all()}
        by_key = {
            build_key(e, dept_codes, acc_codes): e
            for e in AuditException.objects.filter(run=self.audit_run)
        }
        checks = {
            # subject → hand-computed amount (declared rows − thresholds)
            ("T-BUD-01", "combo:D-LOG:5604"): D("44500"),   # 68500−24000
            ("T-BUD-01", "combo:D-IT:5603"): D("0"),         # 18000−18000
            ("T-BUD-03", "combo:D-LOG:5601:m02"): D("2000"),  # 3000−1000
            ("T-BUD-03", "combo:D-LOG:5604:m10"): D("17000"),  # 19000−2000
        }
        for (code, subject), amount in checks.items():
            matches = [e for (c, _t, s), e in by_key.items()
                       if c == code and s == subject]
            self.assertEqual(len(matches), 1, f"{code} × {subject}")
            self.assertEqual(matches[0].amount, amount,
                             f"{code} × {subject}")


# ============================================================ 8) exceptions
class ExceptionLifecycleTests(DatasetBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.audit_run = cls.run_all_tests()

    def test_every_exception_has_required_traceability_fields(self):
        for e in AuditException.objects.filter(run=self.audit_run):
            self.assertEqual(e.run_id, self.audit_run.pk)
            self.assertIsNotNone(e.result_id)
            self.assertIsNotNone(e.test_id)
            self.assertEqual(e.test_code, e.test.test_code)
            self.assertIn(e.source_type,
                          ("expense", "procurement", "budget_combination"))
            self.assertTrue(e.source_id)
            self.assertTrue(e.source_ref)
            self.assertTrue(e.exception_type)
            self.assertTrue(e.title)
            self.assertTrue(e.explanation)
            self.assertIn(e.control_severity, ("S1", "S2", "S3"))
            self.assertIn(e.risk_level, ("High", "Medium", "Low"))
            self.assertRegex(e.risk_rule_ref, r"^RR-0[1-6]$")
            self.assertEqual(e.status, AuditException.STATUS_OPEN)
            self.assertTrue(e.detected_at)
            self.assertEqual(e.auditor_action, e.test.auditor_action)

    def test_status_lifecycle_open_acknowledged_resolved(self):
        exc = self.exception_for(
            self.audit_run, ("T-EXP-02", "Unapproved Payment", "expense:E-UNAP"))
        self.assertIsNotNone(exc)
        url = reverse("audit:exception_update", args=[exc.pk])
        self.client.force_login(self.ds_auditor)

        self.client.post(url, {"status": "acknowledged",
                               "status_note": "قيد الدراسة"})
        exc.refresh_from_db()
        self.assertEqual(exc.status, "acknowledged")
        self.assertEqual(exc.handled_by, self.ds_auditor)
        self.assertIsNotNone(exc.handled_at)
        log = AuditLog.objects.filter(
            action="entity_updated", entity_type="audit_exception",
            entity_id=exc.pk).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.diff["status"]["before"], "open")
        self.assertEqual(log.diff["status"]["after"], "acknowledged")

        self.client.post(url, {"status": "resolved",
                               "status_note": "أُغلق بعد التحقق"})
        exc.refresh_from_db()
        self.assertEqual(exc.status, "resolved")
        self.assertEqual(exc.status_note, "أُغلق بعد التحقق")

        self.client.post(url, {"status": "open", "status_note": ""})
        exc.refresh_from_db()
        self.assertEqual(exc.status, "open")
        self.assertIsNone(exc.handled_by)
        self.assertIsNone(exc.handled_at)

    def test_lifecycle_rbac(self):
        exc = AuditException.objects.filter(run=self.audit_run).first()
        url = reverse("audit:exception_update", args=[exc.pk])
        for user in (self.ds_mgmt, self.ds_finance):
            self.client.force_login(user)
            resp = self.client.post(url, {"status": "resolved"})
            self.assertEqual(resp.status_code, 403, user.username)
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("audit:exception_detail", args=[exc.pk]))
        self.assertEqual(resp.status_code, 200)


# ============================================================ 9) risk
class RiskTests(DatasetBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.audit_run = cls.run_all_tests()

    def test_classify_risk_six_bands_from_db_parameters(self):
        params = AuditTest.objects.get(test_code="T-EXP-02").parameters
        # engine reads its bands from the DB parameter blob — same call
        a3, a2 = engine._bands(params)
        self.assertEqual((a3, a2), (10000.0, 2000.0))
        cases = [
            ((D("10000"), "S2"), ("High", "RR-01")),     # ≥ a3 boundary
            ((D("9999.99"), "S3"), ("High", "RR-02")),   # < a3, ≥ a2, S3
            ((D("9999.99"), "S2"), ("Medium", "RR-04")),
            ((D("2000"), "S3"), ("High", "RR-02")),      # a2 boundary
            ((D("1999.99"), "S3"), ("Medium", "RR-03")),
            ((D("1999.99"), "S2"), ("Low", "RR-05")),
            ((D("1999.99"), "S1"), ("Low", "RR-06")),
            ((D("0"), "S1"), ("Low", "RR-06")),          # early-consumption
        ]
        for (amount, severity), expected in cases:
            self.assertEqual(
                engine.classify_risk(amount, severity, params), expected,
                f"{amount} / {severity}")

    def test_stored_risk_spot_checks(self):
        dept_codes = {d.pk: d.code for d in Department.objects.all()}
        acc_codes = {a.pk: a.code for a in Account.objects.all()}
        by_pair = {}
        for e in AuditException.objects.filter(run=self.audit_run):
            k = build_key(e, dept_codes, acc_codes)
            by_pair[(k[0], k[2])] = e          # (test_code, subject)
        for (code, subject), expected in RISK_SPOT_CHECKS.items():
            exc = by_pair.get((code, subject))
            self.assertIsNotNone(exc, f"missing exception: {code}/{subject}")
            self.assertEqual(
                (exc.risk_level, exc.risk_rule_ref), expected,
                f"{code} × {subject}")

    def test_risk_distribution_matches_declaration(self):
        dist = dict(Counter(
            AuditException.objects.filter(run=self.audit_run)
            .values_list("risk_level", flat=True)))
        self.assertEqual(dist, RISK_COUNTS)
        self.assertEqual(sum(RISK_COUNTS.values()), EXPECTED_TOTAL)


# ============================================================ 10) reports
class ReportTests(DatasetBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.audit_run = cls.run_all_tests()

    def test_exception_register_rows_and_summary(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("reports:detail", args=["exception-register"]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["row_count"], EXPECTED_TOTAL)
        summary = {s["label"]: s["value"] for s in resp.context["summary"]}
        self.assertEqual(summary["إجمالي الاستثناءات"], "28")
        self.assertEqual(summary["High"], str(RISK_COUNTS["High"]))
        self.assertEqual(summary["Medium"], str(RISK_COUNTS["Medium"]))
        self.assertEqual(summary["Low"], str(RISK_COUNTS["Low"]))

    def test_budget_vs_actual_rows_hand_checked(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("reports:detail", args=["budget-vs-actual"]))
        self.assertEqual(resp.context["row_count"], 12)
        target = None
        for row in resp.context["rows"]:
            if (row["department"]["d"] == "اللوجستيات"
                    and row["account"]["d"] == "مستلزمات تشغيلية"):
                target = row
                break
        self.assertIsNotNone(target)
        self.assertEqual(target["budget"]["v"], D("24000"))
        self.assertEqual(target["actual"]["v"], D("68500"))
        self.assertEqual(target["variance"]["v"], D("-44500"))

    def test_procurement_exceptions_report(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("reports:detail", args=["procurement-exceptions"]))
        self.assertEqual(resp.context["row_count"], 8)

    def test_test_results_report_all_flagged(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("reports:detail", args=["test-results"]))
        self.assertEqual(resp.context["row_count"], 14)
        summary = {s["label"]: s["value"] for s in resp.context["summary"]}
        self.assertEqual(summary["مُعلَّم"], "14")
        self.assertEqual(summary["ناجح"], "0")
        self.assertEqual(summary["فاشل"], "0")

    def test_export_csv_bom_and_full_register(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("reports:export", args=["exception-register", "csv"]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Type"].startswith("text/csv"))
        body = resp.content
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))   # Excel BOM
        text = body.decode("utf-8-sig")
        self.assertIn("إجمالي الاستثناءات", text)
        self.assertIn("T-EXP-02", text)
        # header + 28 rows + blank + summary section
        self.assertGreaterEqual(len(text.splitlines()), 28 + 4)

    def test_reports_rbac(self):
        self.client.force_login(self.ds_mgmt)      # reports.view only
        resp = self.client.get(
            reverse("reports:detail", args=["risk-report"]))
        self.assertEqual(resp.status_code, 200)
        self.client.logout()
        resp = self.client.get(
            reverse("reports:detail", args=["risk-report"]))
        self.assertEqual(resp.status_code, 302)     # → login


# ============================================================ 11) dashboard
class DashboardQueryTests(DatasetBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.audit_run = cls.run_all_tests()

    def test_kpis_after_engine_run(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(reverse("dashboard:index"))
        kpis = resp.context["kpis"]
        self.assertEqual(kpis["effective_budget"], D("69000"))
        self.assertEqual(kpis["actual"], D("123190"))
        self.assertEqual(kpis["variance"], D("-54190"))
        self.assertEqual(kpis["exceptions"], EXPECTED_TOTAL)
        self.assertEqual(kpis["high_risk"], RISK_COUNTS["High"])
        self.assertEqual(kpis["proc_exceptions"], 8)
        self.assertEqual(kpis["oob_count"], 8)
        self.assertEqual(kpis["oob_amount"], D("18550"))

    def test_risk_status_and_result_queries(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(reverse("dashboard:index"))
        ctx = resp.context
        self.assertEqual(dict(ctx["risk_counts"]), RISK_COUNTS)
        status = {k: v["n"] for k, v in ctx["status_counts"].items()}
        self.assertEqual(status["open"], 28)
        self.assertEqual(status["acknowledged"], 0)
        self.assertEqual(status["resolved"], 0)
        self.assertEqual(len(ctx["recent_exceptions"]), 6)
        self.assertEqual(len(ctx["result_rows"]), 14)
        self.assertTrue(all(r["status"] == "flagged"
                            for r in ctx["result_rows"]))
        self.assertEqual(ctx["latest_run"].pk, self.audit_run.pk)

    def test_department_filter_query(self):
        self.client.force_login(self.ds_auditor)
        dept = Department.objects.get(code="D-LOG")
        resp = self.client.get(
            reverse("dashboard:index"), {"department": dept.pk})
        kpis = resp.context["kpis"]
        # hand calc: 68500 (5604) + 10000 (5601) + 850 (5603) = 79350
        self.assertEqual(kpis["actual"], D("79350"))
        self.assertEqual(kpis["effective_budget"], D("36000"))

    def test_period_filter_query_october(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(
            reverse("dashboard:index"), {"period": self.period_pk(10)})
        kpis = resp.context["kpis"]
        # budget 2000+1000+1500+750+500 = 5750
        # actual 19000 (E-LOG-10) + 1800 (E-ITS-10) + 1800 (E-OB1)
        self.assertEqual(kpis["effective_budget"], D("5750"))
        self.assertEqual(kpis["actual"], D("22600"))

    def test_risk_filter_query_high_only(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(reverse("dashboard:index"), {"risk": "High"})
        kpis = resp.context["kpis"]
        self.assertEqual(kpis["exceptions"], RISK_COUNTS["High"])
        self.assertEqual(kpis["high_risk"], RISK_COUNTS["High"])

    def test_department_rows_sorted_by_absolute_variance(self):
        self.client.force_login(self.ds_auditor)
        resp = self.client.get(reverse("dashboard:index"))
        rows = resp.context["dept_rows"]
        first = rows[0]
        self.assertEqual(first["name"], "اللوجستيات")
        # hand calc: budget 36000 − actual 79350 = −43350
        self.assertEqual(first["variance"], D("-43350"))
        self.assertEqual(first["budget"], D("36000"))
        self.assertEqual(first["actual"], D("79350"))
