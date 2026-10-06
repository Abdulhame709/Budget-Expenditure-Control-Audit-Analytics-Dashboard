from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.budget import forms, services
from apps.budget.models import (
    BudgetPlan,
    BudgetPlanLine,
    BudgetPlanSalaryComponent,
    BudgetPlanSection,
)
from apps.reference.models import Account, Currency, Department, Employee, FiscalYear


User = get_user_model()
PASSWORD = "S3cure-Demo-Pass!"


class BudgetPlanFixture(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="YER")
        self.fiscal_year = FiscalYear.objects.create(
            code="FY2027", name="السنة المالية 2027", year=2027,
            start_date=date(2027, 1, 1), end_date=date(2027, 12, 31),
        )
        self.finance = Department.objects.create(code="FIN", name="المالية")
        self.operations = Department.objects.create(code="OPS", name="التشغيل")
        self.employee = Employee.objects.create(
            code="EMP-001", full_name="موظف المالية", department=self.finance,
        )
        self.main_account = Account.objects.create(
            code="5100", name="تكلفة مبيعات المخزون - التذاكر",
            account_type="expense",
        )
        self.analytical_account = Account.objects.create(
            code="5101", name="تكلفة مطبوعات التذاكر",
            account_type="expense", level=6, ledger_type="sub",
            parent=self.main_account,
        )
        self.other_main_account = Account.objects.create(
            code="5200", name="حساب رئيسي آخر", account_type="expense",
        )
        self.other_account = Account.objects.create(
            code="5201", name="حساب تحليلي آخر", account_type="expense",
            level=6, ledger_type="sub", parent=self.other_main_account,
        )
        self.plan = BudgetPlan.objects.create(
            name="الموازنة التفصيلية", fiscal_year=self.fiscal_year,
            currency=self.currency,
        )
        self.section = BudgetPlanSection.objects.create(
            plan=self.plan, name="تفصيلي تكلفة المبيعات", position=1,
            department=self.finance,
            default_main_account=self.main_account,
        )

    def make_line(self, **overrides):
        values = {
            "section": self.section,
            "position": self.section.lines.count() + 1,
            "display_name": "قيمة التذاكر المباعة",
            "row_type": BudgetPlanLine.TYPE_DETAIL,
            "main_account": self.main_account,
            "analytical_account": self.analytical_account,
            "department": self.finance,
            "input_mode": BudgetPlanLine.INPUT_ANNUAL,
            "distribution_method": BudgetPlanLine.DIST_EQUAL,
            "annual_amount": Decimal("1200.00"),
        }
        values.update(overrides)
        return BudgetPlanLine.objects.create(**values)


class BudgetPlanValidationTests(BudgetPlanFixture):
    def test_section_department_is_unique_inside_plan(self):
        duplicate = BudgetPlanSection(
            plan=self.plan, name="قسم مكرر", position=2, department=self.finance,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_line_inherits_section_department(self):
        line = self.make_line(department=None)
        line.full_clean()
        self.assertEqual(line.department, self.finance)

    def test_line_rejects_department_different_from_section(self):
        line = self.make_line(department=self.operations)
        with self.assertRaises(ValidationError) as ctx:
            line.full_clean()
        self.assertIn("department", ctx.exception.error_dict)

    def test_line_form_limits_department_and_employees_to_section(self):
        form = forms.BudgetPlanLineForm(section=self.section)
        self.assertEqual(list(form.fields["department"].queryset), [self.finance])
        self.assertEqual(list(form.fields["employee"].queryset), [self.employee])
        self.assertTrue(form.fields["department"].disabled)

    def test_linked_accounts_must_be_level_five(self):
        self.other_account.level = 6
        self.other_account.save(update_fields=["level"])
        line = self.make_line(analytical_account=self.other_account)
        with self.assertRaises(ValidationError) as ctx:
            line.full_clean()
        self.assertIn("analytical_account", ctx.exception.error_dict)

    def test_employee_must_belong_to_selected_department(self):
        line = self.make_line(department=self.operations, employee=self.employee)
        with self.assertRaises(ValidationError) as ctx:
            line.full_clean()
        self.assertIn("employee", ctx.exception.error_dict)

    def test_parent_line_must_be_in_same_section(self):
        other_section = BudgetPlanSection.objects.create(
            plan=self.plan, name="قسم آخر", position=2,
        )
        parent = self.make_line()
        line = BudgetPlanLine(
            section=other_section, parent=parent, position=1,
            display_name="بند تابع",
        )
        with self.assertRaises(ValidationError) as ctx:
            line.full_clean()
        self.assertIn("parent", ctx.exception.error_dict)

    def test_rejects_cycle_in_line_tree(self):
        parent = self.make_line()
        child = self.make_line(position=2, display_name="بند فرعي", parent=parent)
        parent.parent = child
        with self.assertRaises(ValidationError) as ctx:
            parent.full_clean()
        self.assertIn("parent", ctx.exception.error_dict)


class BudgetPlanCalculationTests(BudgetPlanFixture):
    def test_quantity_price_calculation_and_equal_distribution(self):
        line = self.make_line(
            input_mode=BudgetPlanLine.INPUT_QUANTITY_PRICE,
            quantity=Decimal("3"), unit_price=Decimal("100.01"), annual_amount=0,
        )
        values = services.sync_plan_line_amounts(line)
        line.refresh_from_db()
        self.assertEqual(line.annual_amount, Decimal("300.03"))
        self.assertEqual(sum(values.values()), line.annual_amount)
        self.assertEqual(len(line.period_amounts.all()), 12)

    def test_periodic_calculation_and_selected_month_distribution(self):
        line = self.make_line(
            input_mode=BudgetPlanLine.INPUT_PERIODIC,
            periodic_amount=Decimal("250"), periods_count=4, annual_amount=0,
            distribution_method=BudgetPlanLine.DIST_SELECTED_MONTHS,
            selected_months=[1, 4, 7, 10],
        )
        values = services.sync_plan_line_amounts(line)
        self.assertEqual(values[1], Decimal("250.00"))
        self.assertEqual(values[2], Decimal("0"))
        self.assertEqual(sum(values.values()), Decimal("1000.00"))

    def test_days_workers_calculation(self):
        line = self.make_line(
            input_mode=BudgetPlanLine.INPUT_DAYS_WORKERS,
            days_count=Decimal("6"), workers_count=5,
            rate_amount=Decimal("2500"), annual_amount=0,
        )
        values = services.sync_plan_line_amounts(line)
        line.refresh_from_db()
        self.assertEqual(line.annual_amount, Decimal("75000.00"))
        self.assertEqual(sum(values.values()), Decimal("75000.00"))

    def test_hours_workers_calculation(self):
        line = self.make_line(
            input_mode=BudgetPlanLine.INPUT_HOURS_WORKERS,
            hours_count=Decimal("7.5"), workers_count=4,
            rate_amount=Decimal("1200"), annual_amount=0,
        )
        services.sync_plan_line_amounts(line)
        line.refresh_from_db()
        self.assertEqual(line.annual_amount, Decimal("36000.00"))

    def test_percentage_calculation(self):
        line = self.make_line(
            input_mode=BudgetPlanLine.INPUT_PERCENTAGE,
            base_amount=Decimal("125000"), percentage_rate=Decimal("7.5"),
            annual_amount=0,
        )
        services.sync_plan_line_amounts(line)
        line.refresh_from_db()
        self.assertEqual(line.annual_amount, Decimal("9375.00"))

    def test_salary_components_calculation_and_monthly_distribution(self):
        line = self.make_line(
            input_mode=BudgetPlanLine.INPUT_SALARY_COMPONENTS,
            distribution_method=BudgetPlanLine.DIST_NONE,
            employee=self.employee,
            annual_amount=0,
        )
        BudgetPlanSalaryComponent.objects.create(
            line=line, position=1, name="الراتب الأساسي",
            amount=Decimal("100000"), periods_count=12,
            is_percentage_base=True,
        )
        BudgetPlanSalaryComponent.objects.create(
            line=line, position=2, name="بدل مواصلات",
            amount=Decimal("20000"), periods_count=12,
        )
        BudgetPlanSalaryComponent.objects.create(
            line=line, position=3, name="تأمينات جهة العمل",
            calculation_method=BudgetPlanSalaryComponent.METHOD_PERCENTAGE,
            percentage_rate=Decimal("11"),
        )
        BudgetPlanSalaryComponent.objects.create(
            line=line, position=4, name="إكرامية رمضان",
            calculation_method=BudgetPlanSalaryComponent.METHOD_SEASONAL,
            amount=Decimal("50000"), payment_month=3,
        )
        values = services.sync_plan_line_amounts(line)
        line.refresh_from_db()
        self.assertEqual(values[1], Decimal("131000.00"))
        self.assertEqual(values[3], Decimal("181000.00"))
        self.assertEqual(line.annual_amount, Decimal("1622000.00"))

    def test_monthly_input_becomes_annual_total(self):
        line = self.make_line(
            input_mode=BudgetPlanLine.INPUT_MONTHLY,
            distribution_method=BudgetPlanLine.DIST_MANUAL,
            annual_amount=0,
        )
        monthly = {month: Decimal(month * 10) for month in range(1, 13)}
        services.sync_plan_line_amounts(line, monthly)
        line.refresh_from_db()
        self.assertEqual(line.annual_amount, Decimal("780.00"))

    def test_manual_distribution_must_equal_annual_amount(self):
        line = self.make_line(distribution_method=BudgetPlanLine.DIST_MANUAL)
        with self.assertRaises(ValidationError):
            services.sync_plan_line_amounts(line, {1: Decimal("100")})


class BudgetPlanOutputTests(BudgetPlanFixture):
    def test_three_outputs_share_the_same_totals(self):
        first = self.make_line(annual_amount=Decimal("1200"))
        second = self.make_line(
            position=2, display_name="تكلفة أجور تختيم التذاكر",
            analytical_account=Account.objects.create(
                code="5102", name="تكلفة أجور تختيم التذاكر",
                account_type="expense", parent=self.main_account,
            ),
            annual_amount=Decimal("600"),
        )
        services.sync_plan_line_amounts(first)
        services.sync_plan_line_amounts(second)

        detailed_total = sum(
            item["line"].annual_amount
            for section in services.detailed_plan_output(self.plan)
            for item in section["lines"]
            if item["line"].input_mode != BudgetPlanLine.INPUT_NONE
        )
        monthly_total = sum(row["annual_total"] for row in services.monthly_plan_output(self.plan))
        summary = services.summary_plan_output(self.plan)
        self.assertEqual(detailed_total, Decimal("1800.00"))
        self.assertEqual(monthly_total, detailed_total)
        self.assertEqual(summary[0]["annual_total"], detailed_total)
        self.assertEqual(sum(summary[0]["monthly"]), detailed_total)

    def test_total_row_can_aggregate_multiple_sections_without_double_counting(self):
        second_section = BudgetPlanSection.objects.create(
            plan=self.plan, name="قسم ثانٍ", position=2,
        )
        first = self.make_line(annual_amount=Decimal("1200"))
        second = BudgetPlanLine.objects.create(
            section=second_section, position=1, display_name="بند ثانٍ",
            main_account=self.main_account,
            analytical_account=self.analytical_account,
            input_mode=BudgetPlanLine.INPUT_ANNUAL,
            distribution_method=BudgetPlanLine.DIST_EQUAL,
            annual_amount=Decimal("600"),
        )
        total = BudgetPlanLine.objects.create(
            section=self.section, position=2, display_name="إجمالي القسمين",
            row_type=BudgetPlanLine.TYPE_TOTAL,
            input_mode=BudgetPlanLine.INPUT_NONE,
        )
        total.aggregate_sections.set([self.section, second_section])
        services.sync_plan_line_amounts(first)
        services.sync_plan_line_amounts(second)
        detailed = services.detailed_plan_output(self.plan)
        total_row = next(
            item for section in detailed for item in section["lines"]
            if item["line"].pk == total.pk
        )
        self.assertEqual(total_row["annual_amount"], Decimal("1800.00"))
        self.assertEqual(
            services.summary_plan_output(self.plan)[0]["annual_total"],
            Decimal("1800.00"),
        )

    def test_detailed_output_orders_children_after_parent_with_depth(self):
        parent = self.make_line(
            row_type=BudgetPlanLine.TYPE_MAIN_ACCOUNT,
            input_mode=BudgetPlanLine.INPUT_NONE,
            distribution_method=BudgetPlanLine.DIST_NONE,
            annual_amount=0,
        )
        child = self.make_line(position=2, parent=parent)
        items = services.detailed_plan_output(self.plan)[0]["lines"]
        self.assertEqual([item["line"].pk for item in items], [parent.pk, child.pk])
        self.assertEqual([item["depth"] for item in items], [0, 1])


class BudgetPlanHttpTests(BudgetPlanFixture):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="plan_admin", password=PASSWORD)
        UserRole.objects.create(user=self.admin, role=Role.objects.get(code="admin"))
        self.auditor = User.objects.create_user(username="plan_auditor", password=PASSWORD)
        UserRole.objects.create(user=self.auditor, role=Role.objects.get(code="auditor"))

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_auditor_views_plan_but_cannot_edit(self):
        client = self.client_for(self.auditor)
        self.assertEqual(client.get(reverse("budget:plan_detail", args=[self.plan.pk])).status_code, 200)
        self.assertEqual(client.get(reverse("budget:plan_edit", args=[self.plan.pk])).status_code, 403)

    def test_plan_and_department_pages_link_to_each_other(self):
        client = self.client_for(self.admin)
        plan_response = client.get(reverse("budget:plan_detail", args=[self.plan.pk]))
        self.assertContains(
            plan_response, reverse("reference:department_detail", args=[self.finance.pk]),
        )
        department_response = client.get(
            reverse("reference:department_detail", args=[self.finance.pk]),
        )
        self.assertContains(department_response, self.plan.name)
        self.assertContains(department_response, "نماذج الموازنة المرتبطة")

    def test_admin_creates_section_from_reference_department(self):
        response = self.client_for(self.admin).post(
            reverse("budget:plan_section_create", args=[self.plan.pk]),
            {
                "department": str(self.operations.pk),
                "name": "",
                "description": "",
                "position": "2",
                "default_main_account": str(self.main_account.pk),
            },
        )
        self.assertRedirects(response, reverse("budget:plan_detail", args=[self.plan.pk]))
        section = BudgetPlanSection.objects.get(plan=self.plan, department=self.operations)
        self.assertEqual(section.name, self.operations.name)

    def test_locked_plan_rejects_line_creation(self):
        self.plan.status = BudgetPlan.STATUS_APPROVED
        self.plan.save(update_fields=["status"])
        response = self.client_for(self.admin).get(
            reverse("budget:plan_line_create", args=[self.section.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_dependent_dropdowns_filter_accounts_and_employees(self):
        client = self.client_for(self.admin)
        response = client.get(
            reverse("budget:plan_analytical_accounts"),
            {"main_account": self.main_account.pk},
        )
        ids = {item["id"] for item in response.json()["results"]}
        self.assertEqual(ids, {self.analytical_account.pk})
        response = client.get(
            reverse("budget:plan_department_employees"),
            {"department": self.finance.pk},
        )
        ids = {item["id"] for item in response.json()["results"]}
        self.assertEqual(ids, {self.employee.pk})

    def test_line_editor_renders_main_and_analytical_account_fields(self):
        response = self.client_for(self.admin).get(
            reverse("budget:plan_line_create", args=[self.section.pk]),
        )
        self.assertContains(response, 'id="id_main_account"')
        self.assertContains(response, 'id="id_analytical_account"')
        self.assertContains(response, self.main_account.name)

    def test_add_child_link_prefills_parent(self):
        parent = self.make_line()
        response = self.client_for(self.admin).get(
            reverse("budget:plan_line_create", args=[self.section.pk]),
            {"parent": parent.pk},
        )
        self.assertEqual(response.context["form"].initial["parent"], str(parent.pk))
        self.assertContains(response, "يتبع للبند / المجموعة")

    def test_admin_moves_sibling_line_and_toggles_inclusion(self):
        first = self.make_line(position=1, display_name="الأول")
        second = self.make_line(position=2, display_name="الثاني")
        client = self.client_for(self.admin)
        response = client.post(
            reverse("budget:plan_line_move", args=[second.pk, "up"]),
        )
        self.assertRedirects(response, reverse("budget:plan_detail", args=[self.plan.pk]))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.position, second.position), (2, 1))

        response = client.post(reverse("budget:plan_line_toggle_included", args=[second.pk]))
        self.assertRedirects(response, reverse("budget:plan_detail", args=[self.plan.pk]))
        second.refresh_from_db()
        self.assertFalse(second.is_included)

    def test_copy_salary_line_copies_its_components(self):
        line = self.make_line(
            display_name="راتب موظف",
            input_mode=BudgetPlanLine.INPUT_SALARY_COMPONENTS,
            distribution_method=BudgetPlanLine.DIST_NONE,
            employee=self.employee,
            annual_amount=0,
        )
        BudgetPlanSalaryComponent.objects.create(
            line=line, position=1, name="الراتب الأساسي",
            amount=Decimal("100000"), periods_count=12,
            is_percentage_base=True,
        )
        services.sync_plan_line_amounts(line)
        response = self.client_for(self.admin).post(
            reverse("budget:plan_line_copy", args=[line.pk]),
        )
        self.assertRedirects(response, reverse("budget:plan_detail", args=[self.plan.pk]))
        copied = BudgetPlanLine.objects.get(display_name="راتب موظف - نسخة")
        self.assertEqual(copied.salary_components.count(), 1)
        self.assertEqual(copied.annual_amount, Decimal("1200000.00"))
        self.assertEqual(copied.salary_components.get().created_by, self.admin)

    def test_title_row_is_saved_without_amount_or_account_links(self):
        data = {
            "position": "1",
            "row_type": BudgetPlanLine.TYPE_TITLE,
            "display_name": "عنوان المجموعة",
            "main_account": str(self.main_account.pk),
            "analytical_account": str(self.analytical_account.pk),
            "department": str(self.finance.pk),
            "employee": str(self.employee.pk),
            "unit_of_measure": "ريال",
            "input_mode": BudgetPlanLine.INPUT_ANNUAL,
            "distribution_method": BudgetPlanLine.DIST_EQUAL,
            "annual_amount": "1200",
            "quantity": "0",
            "unit_price": "0",
            "periodic_amount": "0",
            "periods_count": "0",
            "estimation_basis": "عنوان تنظيمي",
            "is_included": "on",
        }
        response = self.client_for(self.admin).post(
            reverse("budget:plan_line_create", args=[self.section.pk]), data,
        )
        self.assertRedirects(response, reverse("budget:plan_detail", args=[self.plan.pk]))
        line = BudgetPlanLine.objects.get(display_name="عنوان المجموعة")
        self.assertEqual(line.input_mode, BudgetPlanLine.INPUT_NONE)
        self.assertEqual(line.distribution_method, BudgetPlanLine.DIST_NONE)
        self.assertEqual(line.annual_amount, Decimal("0.00"))
        self.assertIsNone(line.main_account)
        self.assertIsNone(line.analytical_account)

    def test_admin_creates_monthly_line_from_editor(self):
        data = {
            "position": "1",
            "row_type": BudgetPlanLine.TYPE_DETAIL,
            "display_name": "قيمة التذاكر المباعة",
            "main_account": str(self.main_account.pk),
            "analytical_account": str(self.analytical_account.pk),
            "department": str(self.finance.pk),
            "employee": str(self.employee.pk),
            "unit_of_measure": "ريال",
            "input_mode": BudgetPlanLine.INPUT_MONTHLY,
            "distribution_method": BudgetPlanLine.DIST_MANUAL,
            "annual_amount": "0",
            "quantity": "0",
            "unit_price": "0",
            "periodic_amount": "0",
            "periods_count": "0",
            "estimation_basis": "إدخال شهري يدوي",
            "is_included": "on",
        }
        data.update({f"m{month:02d}": "100" for month in range(1, 13)})
        response = self.client_for(self.admin).post(
            reverse("budget:plan_line_create", args=[self.section.pk]), data,
        )
        line = BudgetPlanLine.objects.get(display_name="قيمة التذاكر المباعة")
        self.assertRedirects(response, reverse("budget:plan_detail", args=[self.plan.pk]))
        self.assertEqual(line.annual_amount, Decimal("1200.00"))
        self.assertEqual(line.period_amounts.count(), 12)
        self.assertEqual(
            sum(line.period_amounts.values_list("amount", flat=True)),
            Decimal("1200.00"),
        )

    def test_admin_creates_percentage_line_from_editor(self):
        data = {
            "position": "1",
            "row_type": BudgetPlanLine.TYPE_DETAIL,
            "display_name": "تأمينات بنسبة من الرواتب",
            "main_account": str(self.main_account.pk),
            "analytical_account": str(self.analytical_account.pk),
            "department": str(self.finance.pk),
            "unit_of_measure": "نسبة",
            "input_mode": BudgetPlanLine.INPUT_PERCENTAGE,
            "distribution_method": BudgetPlanLine.DIST_EQUAL,
            "annual_amount": "0",
            "quantity": "0",
            "unit_price": "0",
            "periodic_amount": "0",
            "periods_count": "0",
            "base_amount": "200000",
            "percentage_rate": "7.5",
            "estimation_basis": "7.5% من إجمالي الرواتب",
            "is_included": "on",
        }
        response = self.client_for(self.admin).post(
            reverse("budget:plan_line_create", args=[self.section.pk]), data,
        )
        self.assertRedirects(response, reverse("budget:plan_detail", args=[self.plan.pk]))
        line = BudgetPlanLine.objects.get(display_name="تأمينات بنسبة من الرواتب")
        self.assertEqual(line.annual_amount, Decimal("15000.00"))
        self.assertEqual(
            sum(line.period_amounts.values_list("amount", flat=True)),
            Decimal("15000.00"),
        )

    def test_admin_creates_employee_salary_components_from_editor(self):
        data = {
            "position": "1",
            "row_type": BudgetPlanLine.TYPE_DETAIL,
            "display_name": "استحقاقات موظف المالية",
            "main_account": str(self.main_account.pk),
            "analytical_account": str(self.analytical_account.pk),
            "department": str(self.finance.pk),
            "employee": str(self.employee.pk),
            "unit_of_measure": "موظف",
            "input_mode": BudgetPlanLine.INPUT_SALARY_COMPONENTS,
            "distribution_method": BudgetPlanLine.DIST_NONE,
            "annual_amount": "0",
            "quantity": "0", "unit_price": "0",
            "periodic_amount": "0", "periods_count": "0",
            "estimation_basis": "راتب وبدلات الموظف",
            "is_included": "on",
            "salary-TOTAL_FORMS": "3",
            "salary-INITIAL_FORMS": "0",
            "salary-MIN_NUM_FORMS": "0",
            "salary-MAX_NUM_FORMS": "1000",
            "salary-0-position": "1",
            "salary-0-name": "الراتب الأساسي",
            "salary-0-component_type": BudgetPlanSalaryComponent.TYPE_EARNING,
            "salary-0-calculation_method": BudgetPlanSalaryComponent.METHOD_MONTHLY,
            "salary-0-amount": "100000",
            "salary-0-percentage_rate": "0",
            "salary-0-start_month": "1",
            "salary-0-periods_count": "12",
            "salary-0-is_percentage_base": "on",
            "salary-0-is_active": "on",
            "salary-1-position": "2",
            "salary-1-name": "بدل هاتف",
            "salary-1-component_type": BudgetPlanSalaryComponent.TYPE_EARNING,
            "salary-1-calculation_method": BudgetPlanSalaryComponent.METHOD_MONTHLY,
            "salary-1-amount": "5000",
            "salary-1-percentage_rate": "0",
            "salary-1-start_month": "1",
            "salary-1-periods_count": "12",
            "salary-1-is_active": "on",
            "salary-2-position": "3",
            "salary-2-name": "تأمينات",
            "salary-2-component_type": BudgetPlanSalaryComponent.TYPE_EARNING,
            "salary-2-calculation_method": BudgetPlanSalaryComponent.METHOD_PERCENTAGE,
            "salary-2-amount": "0",
            "salary-2-percentage_rate": "11",
            "salary-2-start_month": "1",
            "salary-2-periods_count": "12",
            "salary-2-is_active": "on",
        }
        response = self.client_for(self.admin).post(
            reverse("budget:plan_line_create", args=[self.section.pk]), data,
        )
        self.assertRedirects(response, reverse("budget:plan_detail", args=[self.plan.pk]))
        line = BudgetPlanLine.objects.get(display_name="استحقاقات موظف المالية")
        self.assertEqual(line.salary_components.count(), 3)
        self.assertEqual(line.annual_amount, Decimal("1392000.00"))
        self.assertEqual(line.salary_components.filter(created_by=self.admin).count(), 3)
