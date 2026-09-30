"""PHASE 11 — اختبارات لوحة المؤشرات التفاعلية.

كل رقم متوقع محسوب يدويًا أو مقابل استعلام ORM مستقل — لا أرقام محفوظة في
القوالب. سقف خط الأساس عند هذه المرحلة:234 اختبارًا قبل إضافات PHASE 11.
"""
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import PERMISSIONS, URL_PERMISSIONS
from apps.audit_register import services as engine
from apps.audit_register.models import AuditException, AuditTest
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

User = get_user_model()
PW = "S3cure-Demo-Pass!"


def make_user(username, role_code):
    user = User.objects.create_user(username=username, password=PW)
    UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


class DashboardFixture(TestCase):
    """FY2026 +12 فترات · موازنة18000 · مصروفات4000 (منها2000 خارج
    الموازنة) · جولة محرك واحدة تُنشئ الاستثناءات والنتائج."""

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
        cls.d2 = Department.objects.create(code="D2", name="إدارة اثنين")
        cls.c1 = ExpenseCategory.objects.create(code="C1", name="تصنيف1")
        cls.c2 = ExpenseCategory.objects.create(code="C2", name="تصنيف2")
        cls.a1 = Account.objects.create(
            code="7101", name="حساب وحد", account_type="expense",
            expense_category=cls.c1)
        cls.a2 = Account.objects.create(
            code="7102", name="حساب اثنين", account_type="expense",
            expense_category=cls.c2)
        cls.a3 = Account.objects.create(
            code="7103", name="حساب خارج", account_type="expense",
            expense_category=cls.c1)
        cls.sup = Supplier.objects.create(code="SUP-D1", name="مورد د1")
        cls.finance = make_user("fin_d11", "finance")
        cls.auditor = make_user("aud_d11", "auditor")
        cls.mgmt = make_user("mgmt_d11", "management")
        cls.admin = make_user("admin_d11", "admin")

        bud = Budget.objects.create(fiscal_year=cls.fy, name="ميزانية اللوحة")
        ver = BudgetVersion.objects.create(budget=bud, version=1,
                                           status="approved")
        for dept, acc, monthly in ((cls.d1, cls.a1, D("1000")),
                                   (cls.d2, cls.a2, D("500"))):
            line = BudgetLine(
                version=ver, department=dept, account=acc,
                created_by=cls.finance,
                **{f"m{m:02d}": monthly for m in range(1, 13)})
            line.full_clean()
            line.save()

        # مصروفات:2 داخل الموازنة +1 خارجها (D2×A3 غير مخطّطة)
        Expense.objects.create(
            expense_number="EXP-D11-1", expense_date=date(2026, 1, 10),
            period=cls.periods[0], department=cls.d1, account=cls.a1,
            expense_category=cls.c1, supplier=cls.sup, description="س1",
            amount=D("1500"), currency="USD", payment_method="transfer",
            invoice_reference="INV-D1", approval_reference="DEC-D1",
            created_by=cls.finance)
        Expense.objects.create(
            expense_number="EXP-D11-2", expense_date=date(2026, 2, 10),
            period=cls.periods[1], department=cls.d1, account=cls.a1,
            expense_category=cls.c1, supplier=cls.sup, description="س2",
            amount=D("500"), currency="USD", payment_method="transfer",
            created_by=cls.finance)
        cls.oob_expense = Expense.objects.create(
            expense_number="EXP-D11-3", expense_date=date(2026, 3, 10),
            period=cls.periods[2], department=cls.d2, account=cls.a3,
            expense_category=cls.c1, supplier=cls.sup, description="خارج",
            amount=D("2000"), currency="USD", payment_method="transfer",
            created_by=cls.finance)

        Procurement.objects.create(
            reference_number="PR-D11-1", date=date(2026, 1, 5),
            department=cls.d1, supplier=cls.sup, account=cls.a1,
            description="م1 بلا عروض", amount=D("15000"),
            status="approved", created_by=cls.finance)
        Procurement.objects.create(
            reference_number="PR-D11-2", date=date(2026, 2, 5),
            department=cls.d2, supplier=cls.sup, account=cls.a2,
            description="م2 معلّق", amount=D("4500"), status="pending",
            purchase_order="PO-D2", created_by=cls.finance)

        cls.audit_run = engine.start_run(
            AuditTest.objects.filter(is_active=True), cls.auditor,
            mode="all_active")

    def get_dash(self, params=None):
        return self.client.get(reverse("dashboard:index"), params or {})

    def as_(self, username):
        from django.test import Client
        c = Client()
        c.force_login(User.objects.get(username=username))
        return c


class CatalogAndRbacTests(DashboardFixture):
    def test_catalog_stays_30_and_rule(self):
        self.assertEqual(len(PERMISSIONS), 30)
        self.assertEqual(URL_PERMISSIONS["dashboard:index"],
                         "dashboard.view")

    def test_rbac(self):
        # المستخدمون الأربعة يحملون dashboard.view في المصفوفة المعتمدة
        for uname in ("fin_d11", "aud_d11", "mgmt_d11", "admin_d11"):
            c = self.as_(uname)
            self.assertEqual(
                c.get(reverse("dashboard:index")).status_code, 200, uname)
        # زائر
        self.assertEqual(
            self.client.get(reverse("dashboard:index")).status_code, 302)

    def test_nav_link_on_home(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "لوحة المؤشرات")


class KpiTests(DashboardFixture):
    def test_financial_kpis_hand_computed(self):
        c = self.as_("aud_d11")
        k = c.get(reverse("dashboard:index")).context["kpis"]
        # الموازنة الفعّالة = (1000+500)×12 =18000
        self.assertEqual(k["effective_budget"], D("18000"))
        # التنفيذ =1500+500+2000
        self.assertEqual(k["actual"], D("4000"))
        self.assertEqual(k["variance"], D("14000"))
        self.assertAlmostEqual(float(k["utilization"]),
                               float(D("4000") / D("18000") * 100),
                               places=6)
        # خارج الموازنة = مصروف واحد (D2×A3)
        self.assertEqual(k["oob_amount"], D("2000"))
        self.assertEqual(k["oob_count"], 1)

    def test_exception_kpis_match_orm(self):
        c = self.as_("aud_d11")
        k = c.get(reverse("dashboard:index")).context["kpis"]
        self.assertEqual(k["exceptions"], AuditException.objects.count())
        self.assertEqual(k["high_risk"],
                         AuditException.objects.filter(
                             risk_level="High").count())
        self.assertEqual(k["proc_exceptions"],
                         AuditException.objects.filter(
                             source_type="procurement").count())
        self.assertGreater(k["exceptions"], 0)  # الجولة أنشأت استثناءات

    def test_out_of_budget_detail_lists_row(self):
        c = self.as_("aud_d11")
        ctx = c.get(reverse("dashboard:index")).context
        rows = [r["expense_number"] for r in ctx["oob_rows"]]
        self.assertIn("EXP-D11-3", rows)
        self.assertNotIn("EXP-D11-1", rows)

    def test_question_labels_present(self):
        c = self.as_("aud_d11")
        response = c.get(reverse("dashboard:index"))
        for text in (
            "ما Budget؟", "ما Actual Spend؟", "ما Variance؟",
            "نسبة الاستخدام", "خارج الموازنة", "الإدارات ذات الانحرافات",
            "الحسابات الأعلى صرفًا", "ما الاستثناءات؟",
            "مستويات المخاطر", "نتائج Audit Tests", "الاتجاه الشهري",
        ):
            self.assertContains(response, text)


class FilterTests(DashboardFixture):
    def test_period_filter_january(self):
        c = self.as_("aud_d11")
        ctx = c.get(reverse("dashboard:index"),
                    {"period": self.periods[0].pk}).context
        # يناير فقط: ميزانية1000+500، تنفيذ1500 (EXP-D11-1)
        self.assertEqual(ctx["kpis"]["effective_budget"], D("1500"))
        self.assertEqual(ctx["kpis"]["actual"], D("1500"))
        self.assertEqual(ctx["kpis"]["variance"], D("0"))
        # مصروفات خارج الموازنة في يناير:0 (مصروف خارج هو مارس)
        self.assertEqual(ctx["kpis"]["oob_count"], 0)

    def test_department_filter(self):
        c = self.as_("aud_d11")
        ctx = c.get(reverse("dashboard:index"),
                    {"department": self.d1.pk}).context
        self.assertEqual(ctx["kpis"]["effective_budget"], D("12000"))
        self.assertEqual(ctx["kpis"]["actual"], D("2000"))
        self.assertEqual(len(ctx["dept_rows"]), 1)
        self.assertEqual(ctx["dept_rows"][0]["name"], "إدارة وحدة")
        # الاستثناءات لا تتأثر بفلتر الإدارة (لا يوجد مفتاح إدارة مباشر)
        self.assertEqual(ctx["kpis"]["exceptions"],
                         AuditException.objects.count())

    def test_account_and_category_filters(self):
        c = self.as_("aud_d11")
        ctx = c.get(reverse("dashboard:index"),
                    {"account": self.a1.pk}).context
        self.assertEqual(ctx["kpis"]["effective_budget"], D("12000"))
        self.assertEqual(ctx["kpis"]["actual"], D("2000"))
        ctx = c.get(reverse("dashboard:index"),
                    {"category": self.c2.pk}).context
        self.assertEqual(ctx["kpis"]["effective_budget"], D("6000"))
        self.assertEqual(ctx["kpis"]["actual"], D("0"))

    def test_risk_filter(self):
        c = self.as_("aud_d11")
        high = AuditException.objects.filter(risk_level="High").count()
        ctx = c.get(reverse("dashboard:index"),
                    {"risk": "High"}).context
        self.assertEqual(ctx["kpis"]["exceptions"], high)
        self.assertEqual(ctx["charts"]["risk"]["data"][0], high)
        ctx = c.get(reverse("dashboard:index"),
                    {"risk": "Low"}).context
        self.assertEqual(ctx["kpis"]["exceptions"],
                         AuditException.objects.filter(
                             risk_level="Low").count())

    def test_test_filter(self):
        c = self.as_("aud_d11")
        n = AuditException.objects.filter(
            test_code="T-PROC-01").count()
        self.assertGreater(n, 0)
        ctx = c.get(reverse("dashboard:index"),
                    {"test": "T-PROC-01"}).context
        self.assertEqual(ctx["kpis"]["exceptions"], n)
        # جدول نتائج آخر جولة محدود بالاختبار المختار
        self.assertTrue(all(r["code"] == "T-PROC-01"
                            for r in ctx["result_rows"]))


class DataChangeTests(DashboardFixture):
    def test_new_expense_changes_kpis_and_charts(self):
        """شرط التوقف: تغيير البيانات في القاعدة يغيّر KPIs والرسوم."""
        c = self.as_("aud_d11")
        before = c.get(reverse("dashboard:index")).context
        self.assertEqual(before["kpis"]["actual"], D("4000"))
        self.assertEqual(before["charts"]["monthly"]["actual"][3], 0.0)

        Expense.objects.create(
            expense_number="EXP-D11-NEW", expense_date=date(2026, 4, 10),
            period=self.periods[3], department=self.d1, account=self.a1,
            expense_category=self.c1, supplier=self.sup, description="جديد",
            amount=D("777"), currency="USD", payment_method="transfer",
            created_by=self.finance)
        after = c.get(reverse("dashboard:index")).context
        self.assertEqual(after["kpis"]["actual"], D("4777"))
        self.assertEqual(after["kpis"]["variance"], D("13223"))
        # الاتجاه الشهري: أبريل777
        self.assertEqual(after["charts"]["monthly"]["actual"][3], 777.0)
        # رسم الإدارات: تنفيذ إدارة1 يزيد777
        self.assertEqual(after["charts"]["departments"]["actual"][0],
                         before["charts"]["departments"]["actual"][0] + 777.0)
        # الميزانية لا تتأثر بمصروف جديد
        self.assertEqual(after["kpis"]["effective_budget"],
                         before["kpis"]["effective_budget"])

    def test_new_run_changes_results_chart(self):
        c = self.as_("aud_d11")
        before = c.get(reverse("dashboard:index")).context
        before_run = before["latest_run"].pk
        before_results_sum = sum(before["charts"]["test_results"]["data"])
        self.assertEqual(before_results_sum, 14)  # كل الاختبارات14

        engine.start_run(
            AuditTest.objects.filter(is_active=True), self.auditor,
            mode="all_active")
        after = c.get(reverse("dashboard:index")).context
        self.assertGreater(after["latest_run"].pk, before_run)
        self.assertEqual(sum(after["charts"]["test_results"]["data"]), 14)
        self.assertEqual(after["kpis"]["exceptions"],
                         AuditException.objects.count())


class ChartPayloadTests(DashboardFixture):
    def test_chart_payload_matches_kpis(self):
        c = self.as_("aud_d11")
        ctx = c.get(reverse("dashboard:index")).context
        ch = ctx["charts"]
        self.assertEqual(sum(ch["monthly"]["budget"]),
                         float(ctx["kpis"]["effective_budget"]))
        self.assertEqual(sum(ch["monthly"]["actual"]),
                         float(ctx["kpis"]["actual"]))
        self.assertEqual(ch["risk"]["labels"], ["High", "Medium", "Low"])
        self.assertEqual(
            sum(ch["risk"]["data"]), ctx["kpis"]["exceptions"])
        self.assertEqual(len(ch["monthly"]["labels"]), 12)
        # الحساب الأعلى صرفًا أولًا
        self.assertEqual(ctx["top_accounts"][0]["name"], "حساب وحد")

    def test_template_embeds_json_and_chartjs(self):
        c = self.as_("aud_d11")
        response = c.get(reverse("dashboard:index"))
        self.assertContains(response, 'id="dash-charts"')
        self.assertContains(response, "chart.js@4")
        self.assertContains(response, "chart-departments")
        self.assertContains(response, "chart-monthly")


class EmptyDatabaseTests(TestCase):
    def test_zero_state_renders(self):
        user = User.objects.create_user(username="aud_empty", password=PW)
        UserRole.objects.create(
            user=user, role=Role.objects.get(code="auditor"))
        from django.test import Client
        c = Client()
        c.force_login(user)
        response = c.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        k = response.context["kpis"]
        self.assertEqual(k["effective_budget"], D("0"))
        self.assertEqual(k["actual"], D("0"))
        self.assertEqual(k["exceptions"], 0)
        self.assertIsNone(k["utilization"])
        self.assertEqual(response.context["kpis_fmt"]["utilization"], "—")
