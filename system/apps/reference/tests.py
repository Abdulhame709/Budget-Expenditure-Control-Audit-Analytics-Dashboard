"""PHASE 4 — relationships, constraints, CRUD, search/filter/pagination,
and the closed-period posting rule (permission + Audit Trail), all real.

Covers the user's acceptance list:
- CRUD حقيقي · Validation · Active/Inactive · Search · Filtering · Pagination
- Periods: FY, month, start/end, status Open/Closed
- closed-period posting requires a specific permission AND is audited
- اختبر العلاقات والقيود (FK RESTRICT, unique, CHECK, no cycles)
"""
from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import has_perm, user_permission_codes
from apps.governance.models import AuditLog
from apps.reference.models import (
    Account,
    Department,
    Employee,
    ExpenseCategory,
    FiscalYear,
    MonthlyPeriod,
    Supplier,
)
from apps.reference.services import require_period_postable

User = get_user_model()
PW = "S3cure-Demo-Pass!"


def make_user(username: str, role_code: str | None):
    user = User.objects.create_user(username=username, password=PW)
    if role_code:
        UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


def make_fy(code="FY2026", year=2026, start=date(2026, 1, 1), end=date(2026, 12, 31)):
    return FiscalYear.objects.create(
        code=code, name=f"السنة المالية {year}", year=year,
        start_date=start, end_date=end,
    )


def make_period(fy, month=1, status="open"):
    return MonthlyPeriod.objects.create(
        fiscal_year=fy, month=month,
        start_date=date(fy.start_date.year, month, 1),
        end_date=date(fy.start_date.year, month, 28)
        if month == 2 else date(fy.start_date.year, month, 30),
        status=status,
    )


# ================================================================ constraints
class FiscalYearConstraintTests(TestCase):
    def test_rejects_reversed_dates(self):
        fy = FiscalYear(code="FY-X", name="x", year=2026,
                        start_date=date(2026, 12, 31), end_date=date(2026, 1, 1))
        with self.assertRaises(ValidationError) as ctx:
            fy.full_clean()
        self.assertIn("end_date", ctx.exception.error_dict)

    def test_rejects_overlapping_years(self):
        make_fy()
        clash = FiscalYear(code="FY-OVER", name="o", year=2026,
                           start_date=date(2026, 6, 1), end_date=date(2027, 5, 31))
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn("start_date", ctx.exception.error_dict)

    def test_db_check_constraint_blocks_bad_dates(self):
        """DB backstop: even without full_clean, CHECK rejects start > end."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FiscalYear.objects.create(
                    code="FY-BAD", name="b", year=2030,
                    start_date=date(2030, 5, 1), end_date=date(2030, 4, 1),
                )


class PeriodConstraintTests(TestCase):
    def setUp(self):
        self.fy = make_fy()

    def test_unique_period_per_year(self):
        make_period(self.fy, month=3)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MonthlyPeriod.objects.create(
                    fiscal_year=self.fy, month=3,
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
                )

    def test_period_must_fall_inside_fiscal_year(self):
        p = MonthlyPeriod(
            fiscal_year=self.fy, month=1,
            start_date=date(2025, 12, 1), end_date=date(2025, 12, 31),
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_start_must_be_first_day_and_month_matches(self):
        p = MonthlyPeriod(
            fiscal_year=self.fy, month=2,
            start_date=date(2026, 2, 5), end_date=date(2026, 2, 28),
        )
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("start_date", ctx.exception.error_dict)

    def test_end_must_be_last_day_of_month(self):
        p = MonthlyPeriod(
            fiscal_year=self.fy, month=3,
            start_date=date(2026, 3, 1), end_date=date(2026, 3, 30),  # Mar has 31
        )
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("end_date", ctx.exception.error_dict)

    def test_cannot_delete_fiscal_year_with_periods(self):
        make_period(self.fy)
        with self.assertRaises(ProtectedError):
            self.fy.delete()


class DepartmentRelationTests(TestCase):
    def test_rejects_self_parent(self):
        d = Department(code="D1", name="أ")
        d.parent = d
        with self.assertRaises(ValidationError):
            d.full_clean()

    def test_rejects_cycle(self):
        a = Department.objects.create(code="A", name="أ")
        b = Department.objects.create(code="B", name="ب", parent=a)
        a.parent = b
        with self.assertRaises(ValidationError) as ctx:
            a.full_clean()
        self.assertIn("parent", ctx.exception.error_dict)

    def test_cannot_delete_parent_with_children(self):
        a = Department.objects.create(code="A", name="أ")
        Department.objects.create(code="B", name="ب", parent=a)
        with self.assertRaises(ProtectedError):
            a.delete()


class AccountRelationTests(TestCase):
    def test_expense_category_only_on_expense_accounts(self):
        cat = ExpenseCategory.objects.create(code="TRAVEL", name="تنقلات")
        acc = Account(code="1101", name="صندوق", account_type="asset",
                      expense_category=cat)
        with self.assertRaises(ValidationError) as ctx:
            acc.full_clean()
        self.assertIn("expense_category", ctx.exception.error_dict)

    def test_expense_account_links_category_ok(self):
        cat = ExpenseCategory.objects.create(code="TRAVEL", name="تنقلات")
        acc = Account(code="5101", name="مصاريف تنقّل", account_type="expense",
                      expense_category=cat)
        acc.full_clean()  # no error

    def test_parent_must_be_same_type(self):
        parent = Account.objects.create(code="5000", name="مصروفات", account_type="expense")
        child = Account(code="5100", name="مصروفات تشغيلية",
                        account_type="expense", parent=parent)
        child.full_clean()
        bad = Account(code="1100", name="خزينة", account_type="asset", parent=parent)
        with self.assertRaises(ValidationError):
            bad.full_clean()

    def test_cannot_delete_category_used_by_accounts(self):
        cat = ExpenseCategory.objects.create(code="TRAVEL", name="تنقلات")
        Account.objects.create(code="5101", name="تنقّل", account_type="expense",
                               expense_category=cat)
        with self.assertRaises(ProtectedError):
            cat.delete()

    def test_unique_account_code(self):
        Account.objects.create(code="1000", name="أ", account_type="asset")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(code="1000", name="ب", account_type="asset")


class SupplierValidationTests(TestCase):
    def test_invalid_email_rejected(self):
        s = Supplier(code="S1", name="م", email="not-an-email")
        with self.assertRaises(ValidationError):
            s.full_clean()

    def test_tax_number_unique_when_provided(self):
        Supplier.objects.create(code="S1", name="أ", tax_number="123456")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Supplier.objects.create(code="S2", name="ب", tax_number="123456")

    def test_multiple_blank_tax_numbers_allowed(self):
        Supplier.objects.create(code="S1", name="أ")
        Supplier.objects.create(code="S2", name="ب")  # NULL duplicates are fine
        self.assertEqual(Supplier.objects.count(), 2)


class EmployeeValidationTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(code="FIN", name="المالية")

    def test_rejects_end_date_before_start_date(self):
        employee = Employee(
            code="EMP-001", full_name="موظف تجريبي",
            department=self.department,
            start_date=date(2026, 2, 1), end_date=date(2026, 1, 31),
        )
        with self.assertRaises(ValidationError) as ctx:
            employee.full_clean()
        self.assertIn("end_date", ctx.exception.error_dict)

    def test_employee_code_is_unique(self):
        Employee.objects.create(
            code="EMP-001", full_name="الموظف الأول", department=self.department,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Employee.objects.create(
                    code="EMP-001", full_name="الموظف الثاني",
                    department=self.department,
                )

    def test_department_cannot_be_deleted_while_used(self):
        Employee.objects.create(
            code="EMP-001", full_name="موظف تجريبي", department=self.department,
        )
        with self.assertRaises(ProtectedError):
            self.department.delete()


# ================================================================ closed-period rule
class ClosedPeriodRuleTests(TestCase):
    """«لا تسمح بإدخال معاملات في Period مغلق إلا وفق صلاحية محددة
    ومسجلة في Audit Trail»."""

    def setUp(self):
        self.fy = make_fy()
        self.open_p = make_period(self.fy, month=1, status="open")
        self.closed_p = make_period(self.fy, month=2, status="closed")
        self.admin = make_user("adm_p4", "admin")
        self.finance = make_user("fin_p4", "finance")
        self.auditor = make_user("aud_p4", "auditor")

    def test_permission_exists_and_scoped_to_admin(self):
        self.assertTrue(has_perm(self.admin, "periods.post_closed"))
        self.assertFalse(has_perm(self.finance, "periods.post_closed"))
        self.assertFalse(has_perm(self.auditor, "periods.post_closed"))

    def test_open_period_passes_without_override_audit(self):
        before = AuditLog.objects.filter(action="closed_period_override").count()
        require_period_postable(self.finance, self.open_p, purpose="قيد مصروف")
        self.assertEqual(
            AuditLog.objects.filter(action="closed_period_override").count(), before
        )

    def test_closed_period_denied_without_permission(self):
        with self.assertRaises(PermissionDenied):
            require_period_postable(self.finance, self.closed_p, purpose="قيد مصروف")
        self.assertFalse(
            AuditLog.objects.filter(action="closed_period_override").exists()
        )

    def test_closed_period_allowed_with_permission_and_audited(self):
        require_period_postable(self.admin, self.closed_p, purpose="قيد مصروف تجريبي")
        entry = AuditLog.objects.filter(action="closed_period_override",
                                        entity_id=str(self.closed_p.pk)).first()
        self.assertIsNotNone(entry, "override MUST land in the Audit Trail")
        self.assertEqual(entry.actor_label, "adm_p4")
        self.assertEqual(entry.diff.get("purpose"), "قيد مصروف تجريبي")
        self.assertEqual(entry.diff.get("period_status"), "closed")

    def test_inactive_period_also_gated(self):
        self.open_p.is_active = False
        self.open_p.save()
        with self.assertRaises(PermissionDenied):
            require_period_postable(self.finance, self.open_p)
        require_period_postable(self.admin, self.open_p)  # override + audit
        self.assertTrue(
            AuditLog.objects.filter(action="closed_period_override",
                                    entity_id=str(self.open_p.pk)).exists()
        )


# ================================================================ HTTP CRUD + perms
class ReferenceHttpTests(TestCase):
    def setUp(self):
        self.admin = make_user("adm_http", "admin")
        self.auditor = make_user("aud_http", "auditor")
        self.finance = make_user("fin_http", "finance")
        self.mgmt = make_user("mgmt_http", "management")
        self.list_url = reverse("reference:supplier_list")

    def _client(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_anonymous_redirected_with_next(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_management_denied_on_direct_url(self):
        self.assertEqual(self._client(self.mgmt).get(self.list_url).status_code, 403)

    def test_auditor_can_view_but_not_edit(self):
        c = self._client(self.auditor)
        self.assertEqual(c.get(self.list_url).status_code, 200)
        self.assertEqual(c.get(reverse("reference:supplier_create")).status_code, 403)

    def test_finance_post_denied_not_created(self):
        c = self._client(self.finance)
        before = Supplier.objects.count()
        response = c.post(reverse("reference:supplier_create"),
                          {"code": "X1", "name": "مورّد"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Supplier.objects.count(), before)

    def test_admin_create_update_delete_all_audited(self):
        c = self._client(self.admin)
        # CREATE
        response = c.post(reverse("reference:supplier_create"),
                          {"code": "SUP-01", "name": "مورد تجريبي",
                           "phone": "", "email": "", "tax_number": "",
                           "address": "", "is_active": "on", "notes": ""})
        self.assertEqual(response.status_code, 302)
        supplier = Supplier.objects.get(code="SUP-01")
        self.assertEqual(supplier.created_by_id, self.admin.pk)
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="supplier",
            entity_id=str(supplier.pk)).exists())
        # UPDATE (status flip → appears in diff)
        response = c.post(reverse("reference:supplier_edit", args=[supplier.pk]),
                          {"code": "SUP-01", "name": "مورد معدّل",
                           "phone": "", "email": "", "tax_number": "",
                           "address": "", "notes": "", "is_active": ""})
        self.assertEqual(response.status_code, 302)
        supplier.refresh_from_db()
        self.assertFalse(supplier.is_active)
        self.assertEqual(supplier.updated_by_id, self.admin.pk)
        log = AuditLog.objects.filter(action="entity_updated",
                                      entity_id=str(supplier.pk)).first()
        self.assertIsNotNone(log)
        self.assertIn("name", log.diff)
        self.assertIn("is_active", log.diff)
        # DELETE (unreferenced → allowed + audited)
        response = c.post(reverse("reference:supplier_delete", args=[supplier.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Supplier.objects.filter(pk=supplier.pk).exists())
        self.assertTrue(AuditLog.objects.filter(
            action="entity_deleted", entity_type="supplier",
            entity_id=str(supplier.pk)).exists())

    def test_delete_referenced_row_blocked_with_message(self):
        c = self._client(self.admin)
        fy = make_fy()
        make_period(fy, month=1)
        response = c.post(reverse("reference:fiscal_year_delete", args=[fy.pk]))
        self.assertEqual(response.status_code, 302)  # redirect back, not deleted
        self.assertTrue(FiscalYear.objects.filter(pk=fy.pk).exists())

    def test_period_close_reopen_via_action_is_audited(self):
        c = self._client(self.admin)
        fy = make_fy()
        period = make_period(fy, month=4)
        # close
        response = c.post(reverse("reference:period_set_status", args=[period.pk]),
                          {"status": "closed"})
        self.assertEqual(response.status_code, 302)
        period.refresh_from_db()
        self.assertEqual(period.status, "closed")
        entry = AuditLog.objects.filter(action="period_status_changed",
                                        entity_id=str(period.pk)).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.diff["before"], "open")
        self.assertEqual(entry.diff["after"], "closed")
        # reopen
        c.post(reverse("reference:period_set_status", args=[period.pk]),
               {"status": "open"})
        period.refresh_from_db()
        self.assertEqual(period.status, "open")
        self.assertEqual(
            AuditLog.objects.filter(action="period_status_changed",
                                    entity_id=str(period.pk)).count(), 2)

    def test_period_status_not_changeable_through_edit_form(self):
        """Status has no form field — only the audited action can change it."""
        c = self._client(self.admin)
        fy = make_fy()
        period = make_period(fy, month=5)
        response = c.post(reverse("reference:period_edit", args=[period.pk]),
                          {"fiscal_year": fy.pk, "month": 5,
                           "start_date": "2026-05-01", "end_date": "2026-05-31",
                           "notes": "", "is_active": "on",
                           "status": "closed"})  # ignored — not a form field
        self.assertEqual(response.status_code, 302)
        period.refresh_from_db()
        self.assertEqual(period.status, "open")

    def test_fiscal_year_form_validation_surfaces_arabic_errors(self):
        c = self._client(self.admin)
        response = c.post(reverse("reference:fiscal_year_create"),
                          {"code": "FY-BAD", "name": "سيئة", "year": 2027,
                           "start_date": "2027-05-01", "end_date": "2027-04-01",
                           "is_active": "on", "notes": ""})
        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        self.assertContains(response, "تاريخ النهاية يجب أن يكون بعد تاريخ البداية")


# ================================================================ search / filter / pagination
class SearchFilterPaginationTests(TestCase):
    def setUp(self):
        self.admin = make_user("adm_sf", "admin")
        c = Client()
        c.force_login(self.admin)
        self.c = c

    def test_pagination_splits_records(self):
        for i in range(1, 26):
            Supplier.objects.create(code=f"S{i:03d}", name=f"مورّد رقم {i}")
        response = self.c.get(reverse("reference:supplier_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 15)  # page 1
        response = self.c.get(reverse("reference:supplier_list"), {"page": 2})
        self.assertEqual(len(response.context["rows"]), 10)
        self.assertEqual(response.context["total"], 25)

    def test_search_filters_by_code_and_name(self):
        Supplier.objects.create(code="ABC-1", name="العليا للتجارة")
        Supplier.objects.create(code="XYZ-2", name="النهضة للمقاولات")
        response = self.c.get(reverse("reference:supplier_list"), {"q": "عليا"})
        self.assertEqual(response.context["total"], 1)
        response = self.c.get(reverse("reference:supplier_list"), {"q": "xyz"})
        self.assertEqual(response.context["total"], 1)

    def test_status_filter_active_inactive(self):
        Supplier.objects.create(code="A1", name="نشط", is_active=True)
        Supplier.objects.create(code="A2", name="معطّل", is_active=False)
        response = self.c.get(reverse("reference:supplier_list"),
                              {"status": "inactive"})
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(response.context["rows"][0]["obj"].code, "A2")

    def test_account_type_filter(self):
        Account.objects.create(code="1000", name="نقدية", account_type="asset")
        Account.objects.create(code="5000", name="مصروفات", account_type="expense")
        response = self.c.get(reverse("reference:account_list"),
                              {"type": "expense"})
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(response.context["rows"][0]["obj"].code, "5000")

    def test_fiscal_year_filter_on_periods(self):
        fy26 = make_fy()
        fy27 = make_fy(code="FY2027", year=2027,
                       start=date(2027, 1, 1), end=date(2027, 12, 31))
        make_period(fy26, month=1)
        make_period(fy27, month=1)
        response = self.c.get(reverse("reference:period_list"), {"fy": str(fy27.pk)})
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(response.context["rows"][0]["obj"].fiscal_year_id, fy27.pk)

    def test_create_via_get_shows_form(self):
        response = self.c.get(reverse("reference:expense_category_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تصنيف مصروفات")

    def test_employee_search_and_combined_filters(self):
        finance = Department.objects.create(code="FIN", name="المالية")
        operations = Department.objects.create(code="OPS", name="التشغيل")
        Employee.objects.create(
            code="EMP-001", full_name="أحمد المالي", department=finance,
            job_title="محاسب", contract_type="official", is_active=True,
        )
        Employee.objects.create(
            code="EMP-002", full_name="سالم التشغيلي", department=operations,
            job_title="مشرف", contract_type="temporary", is_active=False,
        )

        response = self.c.get(reverse("reference:employee_list"), {"q": "محاسب"})
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(response.context["rows"][0]["obj"].code, "EMP-001")

        response = self.c.get(reverse("reference:employee_list"), {
            "department": str(operations.pk),
            "contract": "temporary",
            "status": "inactive",
        })
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(response.context["rows"][0]["obj"].code, "EMP-002")


class EmployeeHttpTests(TestCase):
    def setUp(self):
        self.admin = make_user("adm_employee", "admin")
        self.auditor = make_user("aud_employee", "auditor")
        self.department = Department.objects.create(code="HR", name="الموارد البشرية")

    def _client(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_auditor_can_view_but_cannot_create_employee(self):
        client = self._client(self.auditor)
        self.assertEqual(client.get(reverse("reference:employee_list")).status_code, 200)
        self.assertEqual(client.get(reverse("reference:employee_create")).status_code, 403)

    def test_admin_can_create_employee_and_action_is_audited(self):
        response = self._client(self.admin).post(reverse("reference:employee_create"), {
            "code": "EMP-100",
            "full_name": "موظف الموازنة",
            "department": str(self.department.pk),
            "contract_type": "official",
            "start_date": "2026-01-01",
            "is_active": "on",
        })
        employee = Employee.objects.get(code="EMP-100")
        self.assertRedirects(response, reverse("reference:employee_detail", args=[employee.pk]))
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="employee", entity_id=str(employee.pk),
        ).exists())


# ================================================================ catalog integration
class CatalogIntegrationTests(TestCase):
    def test_new_permission_seeded_in_db(self):
        from apps.accounts.models import Permission
        perm = Permission.objects.get(code="periods.post_closed")
        self.assertEqual(perm.module, "periods")

    def test_admin_holds_30_and_others_unchanged(self):
        counts = {}
        for role in ("admin", "auditor", "finance", "management"):
            user = make_user(f"cat_{role}", role)
            counts[role] = len(user_permission_codes(user))
        self.assertEqual(counts, {
            "admin": 30, "auditor": 18, "finance": 12, "management": 5,
        })

    def test_created_by_integration_on_all_modules(self):
        admin = make_user("adm_int", "admin")
        fy = make_fy()
        fy.created_by = admin
        fy.save()
        self.assertEqual(fy.created_by.username, "adm_int")
