"""PHASE 12 — اختبارات نظام التقارير التسعة (كلها من استعلامات حية)."""
import csv
import io
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import PERMISSIONS, URL_PERMISSIONS
from apps.audit_register import services as engine
from apps.audit_register.models import (
    AuditException,
    AuditFinding,
    AuditTest,
    AuditTestResult,
)
from apps.budget.models import Budget, BudgetLine, BudgetVersion
from apps.expenses.models import Expense
from apps.procurement.models import Procurement
from apps.reference.models import (
    Account,
    Department,
    ExpenseCategory,
    FiscalYear,
    MonthlyPeriod,
    Supplier,
)
from apps.reports.builders import REPORTS

User = get_user_model()
PW = "S3cure-Demo-Pass!"


def make_user(username, role_code):
    user = User.objects.create_user(username=username, password=PW)
    UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


class ReportFixture(TestCase):
    """موازنة12000 + مصروف داخل1500 وآخر خارج500 + جولة محرك."""

    @classmethod
    def setUpTestData(cls):
        cls.fy = FiscalYear.objects.create(
            code="FY2026", name="2026", year=2026,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        cls.periods = []
        for m in range(1, 13):
            last = 31 if m in (1, 3, 5, 7, 8, 10, 12) else (
                28 if m == 2 else 30)
            cls.periods.append(MonthlyPeriod.objects.create(
                fiscal_year=cls.fy, month=m,
                start_date=date(2026, m, 1), end_date=date(2026, m, last)))
        cls.d1 = Department.objects.create(code="D1", name="إدارة وحدة")
        cls.c1 = ExpenseCategory.objects.create(code="C1", name="تصنيف1")
        cls.c2 = ExpenseCategory.objects.create(code="C2", name="تصنيف2")
        cls.a1 = Account.objects.create(
            code="7101", name="حساب وحد", account_type="expense",
            expense_category=cls.c1)
        cls.a2 = Account.objects.create(
            code="7102", name="حساب اثنين", account_type="expense",
            expense_category=cls.c2)
        cls.sup = Supplier.objects.create(code="SUP-R1", name="مورد ت1")
        cls.finance = make_user("fin_p12", "finance")
        cls.auditor = make_user("aud_p12", "auditor")
        cls.mgmt = make_user("mgmt_p12", "management")

        bud = Budget.objects.create(fiscal_year=cls.fy, name="ميزانية التقارير")
        ver = BudgetVersion.objects.create(budget=bud, version=1,
                                           status="approved")
        line = BudgetLine(
            version=ver, department=cls.d1, account=cls.a1,
            created_by=cls.finance,
            **{f"m{m:02d}": D("1000") for m in range(1, 13)})
        line.full_clean()
        line.save()

        Expense.objects.create(
            expense_number="EXP-R1", expense_date=date(2026, 1, 10),
            period=cls.periods[0], department=cls.d1, account=cls.a1,
            expense_category=cls.c1, supplier=cls.sup, description="داخل",
            amount=D("1500"), currency="USD", payment_method="transfer",
            invoice_reference="INV-R1", approval_reference="DEC-R1",
            created_by=cls.finance)
        Expense.objects.create(
            expense_number="EXP-R2", expense_date=date(2026, 3, 10),
            period=cls.periods[2], department=cls.d1, account=cls.a2,
            expense_category=cls.c2, supplier=cls.sup, description="خارج",
            amount=D("500"), currency="USD", payment_method="transfer",
            created_by=cls.finance)
        Procurement.objects.create(
            reference_number="PR-R1", date=date(2026, 1, 5),
            department=cls.d1, supplier=cls.sup, account=cls.a1,
            description="بلا عروض", amount=D("15000"),
            status="approved", created_by=cls.finance)
        cls.audit_run = engine.start_run(
            AuditTest.objects.filter(is_active=True), cls.auditor,
            mode="all_active")

    def as_(self, username):
        from django.test import Client
        c = Client()
        c.force_login(User.objects.get(username=username))
        return c


class CatalogRbacTests(ReportFixture):
    def test_catalog_30_and_six_rules(self):
        self.assertEqual(len(PERMISSIONS), 30)
        expect = {
            "reports:list": "reports.view",
            "reports:detail": "reports.view",
            "reports:export": "reports.generate",
        }
        for name, code in expect.items():
            self.assertEqual(URL_PERMISSIONS[name], code)
        self.assertEqual(
            len([k for k in URL_PERMISSIONS if k.startswith("reports:")]), 3)

    def test_rbac(self):
        self.assertEqual(
            self.client.get(reverse("reports:list")).status_code, 302)
        for uname in ("fin_p12", "aud_p12", "mgmt_p12"):
            c = self.as_(uname)
            self.assertEqual(c.get(reverse("reports:list")).status_code,
                             200, uname)
            self.assertEqual(
                c.get(reverse("reports:detail", args=["findings"]))
                .status_code, 200, uname)
        # تصدير: finance/auditor (reports.generate) — management ليس لديه
        self.assertEqual(
            self.as_("fin_p12").get(
                reverse("reports:export", args=["findings", "csv"]))
            .status_code, 200)
        self.assertEqual(
            self.as_("mgmt_p12").get(
                reverse("reports:export", args=["findings", "csv"]))
            .status_code, 403)
        self.assertEqual(
            self.client.get(
                reverse("reports:export", args=["findings", "csv"]))
            .status_code, 302)


class ReportRenderTests(ReportFixture):
    def test_all_nine_render_with_live_rows(self):
        c = self.as_("aud_p12")
        self.assertEqual(len(REPORTS), 9)
        for slug, meta in REPORTS.items():
            response = c.get(reverse("reports:detail", args=[slug]))
            self.assertEqual(response.status_code, 200, slug)
            self.assertContains(response, meta["title_ar"])
            # أعمدة + ملخّص من البناء الحي
            self.assertTrue(response.context["columns"], slug)
            self.assertTrue(response.context["summary"], slug)
            self.assertIsNotNone(response.context["row_count"], slug)

    def test_print_assets_present(self):
        c = self.as_("aud_p12")
        response = c.get(reverse("reports:detail", args=["variance"]))
        self.assertContains(response, "window.print()")
        self.assertContains(response, "print-header")
        self.assertContains(response, "Print / PDF")
        # Print CSS فعلي في ورقة الأنماط
        from django.contrib.staticfiles import finders
        css = open(finders.find("css/app.css"), encoding="utf-8").read()
        self.assertIn("@media print", css)
        self.assertIn(".print-only", css)

    def test_budget_vs_actual_values(self):
        c = self.as_("aud_p12")
        ctx = c.get(
            reverse("reports:detail", args=["budget-vs-actual"])).context
        summary = {s["label"]: s["value"] for s in ctx["summary"]}
        self.assertEqual(summary["Effective Budget"], "12,000.00")
        self.assertEqual(summary["Actual Expenses"], "2,000.00")
        self.assertEqual(summary["Variance"], "10,000.00")
        self.assertEqual(len(ctx["rows"]), 2)
        # صف داخل الموازنة
        r1 = next(r for r in ctx["rows"]
                  if r["account"]["d"] == "حساب وحد")
        self.assertEqual(r1["budget"]["d"], "12,000.00")
        self.assertEqual(r1["actual"]["d"], "1,500.00")
        # صف خارج الموازنة (ميزانية صفر)
        r2 = next(r for r in ctx["rows"]
                  if r["account"]["d"] == "حساب اثنين")
        self.assertEqual(r2["budget"]["d"], "0.00")
        self.assertEqual(r2["actual"]["d"], "500.00")

    def test_out_of_budget_report(self):
        c = self.as_("aud_p12")
        ctx = c.get(reverse("reports:detail", args=["out-of-budget"])).context
        summary = {s["label"]: s["value"] for s in ctx["summary"]}
        self.assertEqual(summary["عدد المصروفات خارج الموازنة"], "1")
        self.assertEqual(summary["Out-of-Budget Amount"], "500.00")
        self.assertEqual(ctx["rows"][0]["expense_number"]["d"], "EXP-R2")

    def test_variance_report_months(self):
        c = self.as_("aud_p12")
        ctx = c.get(reverse("reports:detail", args=["variance"])).context
        #12 شهر × سطر ميزانية واحد (المستخدم الفعلي في مارس1000/500)
        self.assertGreaterEqual(len(ctx["rows"]), 12)
        # مارس — سطر الميزانية (1000) بلا تنفيذ → استهلاك أقل
        mar = next(r for r in ctx["rows"]
                   if r["month"]["d"] == "مارس"
                   and r["account"]["d"] == "حساب وحد")
        self.assertEqual(mar["budget"]["d"], "1,000.00")
        self.assertEqual(mar["actual"]["d"], "0.00")
        self.assertEqual(mar["status"]["d"], "استهلاك أقل")
        # مارس — تنفيذ500 بلا ميزانية للتركيبة → تجاوز
        mar2 = next(r for r in ctx["rows"]
                    if r["month"]["d"] == "مارس"
                    and r["account"]["d"] == "حساب اثنين")
        self.assertEqual(mar2["actual"]["d"], "500.00")
        self.assertEqual(mar2["status"]["d"], "تجاوز")
        jan = next(r for r in ctx["rows"] if r["month"]["d"] == "يناير")
        self.assertEqual(jan["actual"]["d"], "1,500.00")
        self.assertEqual(jan["status"]["d"], "تجاوز")

    def test_expense_analysis_totals(self):
        c = self.as_("aud_p12")
        ctx = c.get(
            reverse("reports:detail", args=["expense-analysis"])).context
        summary = {s["label"]: s["value"] for s in ctx["summary"]}
        self.assertEqual(summary["إجمالي المصروفات"], "2,000.00")
        self.assertEqual(summary["عدد المصروفات"], "2")
        self.assertEqual(len(ctx["rows"]), 2)  # (حساب × تصنيف) مختلفان

    def test_exception_register_and_filters(self):
        c = self.as_("aud_p12")
        total = AuditException.objects.count()
        self.assertGreater(total, 0)
        ctx = c.get(
            reverse("reports:detail", args=["exception-register"])).context
        self.assertEqual(ctx["row_count"], total)
        high = AuditException.objects.filter(risk_level="High").count()
        ctx = c.get(reverse("reports:detail", args=["exception-register"]),
                    {"risk": "High"}).context
        self.assertEqual(ctx["row_count"], high)
        # فترة يناير (تاريخ رصد الجولات ليس يناير) → سجل فارغ
        ctx = c.get(reverse("reports:detail", args=["exception-register"]),
                    {"period": self.periods[0].pk}).context
        self.assertEqual(ctx["row_count"], 0)

    def test_procurement_exceptions_report(self):
        c = self.as_("aud_p12")
        ctx = c.get(reverse("reports:detail",
                            args=["procurement-exceptions"])).context
        expected = AuditException.objects.filter(
            source_type="procurement").count()
        self.assertEqual(ctx["row_count"], expected)
        self.assertGreater(expected, 0)

    def test_test_results_report(self):
        c = self.as_("aud_p12")
        ctx = c.get(reverse("reports:detail", args=["test-results"])).context
        self.assertEqual(ctx["row_count"], AuditTestResult.objects.count())
        # فلتر اختبار
        ctx = c.get(reverse("reports:detail", args=["test-results"]),
                    {"test": "T-PROC-01"}).context
        self.assertTrue(all(r["test_code"]["d"] == "T-PROC-01"
                            for r in ctx["rows"]))
        # فلترة الاتساق مع ملخص الناجح للاختبار نفسه من ORM
        pass_n = AuditTestResult.objects.filter(
            test__test_code="T-PROC-01", status="pass").count()
        summary = {s["label"]: s["value"] for s in ctx["summary"]}
        self.assertEqual(summary["ناجح"], str(pass_n))

    def test_risk_report_rows(self):
        c = self.as_("aud_p12")
        ctx = c.get(reverse("reports:detail", args=["risk-report"])).context
        self.assertEqual(len(ctx["rows"]), 3)
        total = sum(r["exceptions"]["v"] for r in ctx["rows"])
        self.assertEqual(total, AuditException.objects.count())

    def test_findings_report_with_link(self):
        finding = AuditFinding.objects.create(
            finding_code="F-2026-00001", title="نتيجة التقارير",
            criteria="c", condition="d", impact="i", recommendation="r",
            risk_level="High")
        c = self.as_("aud_p12")
        ctx = c.get(reverse("reports:detail", args=["findings"])).context
        self.assertEqual(ctx["row_count"], 1)
        cell = ctx["rows"][0]["finding_code"]
        self.assertEqual(cell["d"], "F-2026-00001")
        self.assertIn(f"/audit/findings/{finding.pk}/", cell["url"])
        # فلتر risk
        ctx = c.get(reverse("reports:detail", args=["findings"]),
                    {"risk": "Low"}).context
        self.assertEqual(ctx["row_count"], 0)

    def test_department_filter_on_budget_report(self):
        c = self.as_("aud_p12")
        ctx = c.get(reverse("reports:detail", args=["budget-vs-actual"]),
                    {"department": self.d1.pk}).context
        self.assertEqual(ctx["row_count"], 2)  # كلتا الحسابين تخص D1
        active = [a["label"] for a in ctx["active_filters"]]
        self.assertIn("الإدارة", active)


class ExportTests(ReportFixture):
    def test_csv_export_bom_and_log(self):
        c = self.as_("aud_p12")
        response = c.get(
            reverse("reports:export", args=["budget-vs-actual", "csv"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        body = response.content
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))  # BOM لـ Excel
        text = body.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0][0], "الإدارة")
        self.assertIn("Effective Budget",
                      [r[0] for r in rows if r])  # سطر الملخص
        from apps.governance.models import AuditLog
        log = AuditLog.objects.get(action="report_exported")
        self.assertEqual(log.entity_id, "budget-vs-actual")
        self.assertEqual(log.actor_label, "aud_p12")
        self.assertEqual(log.diff["format"], "csv")

    def test_xlsx_export_loadable(self):
        c = self.as_("fin_p12")
        response = c.get(
            reverse("reports:export", args=["expense-analysis", "xlsx"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "spreadsheetml", response["Content-Type"])
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(response.content))
        ws = wb.active
        header = [cell.value for cell in ws[1]]
        self.assertIn("الإجمالي", header)
        #1 رأس +2 صفوف + فارغ + الملخّص
        self.assertGreaterEqual(ws.max_row, 5)
        # القيمة رقمية (لا نص ثابت)
        amounts = [r[4] for r in ws.iter_rows(min_row=2, max_row=3,
                                              values_only=True)]
        self.assertTrue(all(isinstance(v, (int, float)) for v in amounts))

    def test_csv_formula_text_is_neutralized(self):
        exception = AuditException.objects.order_by("pk").first()
        self.assertIsNotNone(exception)
        exception.title = '=HYPERLINK("https://invalid")'
        exception.save(update_fields=["title"])
        response = self.as_("aud_p12").get(
            reverse("reports:export", args=["exception-register", "csv"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.content.decode("utf-8-sig"))

    def test_xlsx_formula_text_is_stored_as_text(self):
        exception = AuditException.objects.order_by("pk").first()
        self.assertIsNotNone(exception)
        exception.title = '=HYPERLINK("https://invalid")'
        exception.save(update_fields=["title"])
        response = self.as_("aud_p12").get(
            reverse("reports:export", args=["exception-register", "xlsx"]))
        from openpyxl import load_workbook

        ws = load_workbook(io.BytesIO(response.content), data_only=False).active
        formula_like = [
            cell for row in ws.iter_rows() for cell in row
            if isinstance(cell.value, str) and "HYPERLINK" in cell.value
        ]
        self.assertEqual(len(formula_like), 1)
        self.assertTrue(formula_like[0].value.startswith("'=HYPERLINK"))
        self.assertNotEqual(formula_like[0].data_type, "f")

    def test_export_unknown_slug_400(self):
        c = self.as_("aud_p12")
        response = c.get(
            reverse("reports:export", args=["no-such", "csv"]))
        self.assertEqual(response.status_code, 400)
