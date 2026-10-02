"""PHASE 6 — Actual Expenses: validation, links (Budget/COA/Periods),
closed-period enforcement over HTTP, CRUD+audit, attachment, export,
search/filter — all real responses, no UI hiding.
"""
from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.budget.models import Budget, BudgetLine, BudgetVersion
from apps.expenses import services
from apps.expenses.models import Expense
from apps.governance.models import AuditLog
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
D_ = D

TEMP_MEDIA = tempfile.mkdtemp(prefix="p6_media_")


def make_user(username, role_code):
    user = User.objects.create_user(username=username, password=PW)
    UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


class BaseFixture(TestCase):
    """FY2026 + periods 1,2 open / 3 closed + dimensions + approved budget."""

    @classmethod
    def setUpTestData(cls):
        cls.fy = FiscalYear.objects.create(
            code="FY2026", name="السنة المالية 2026", year=2026,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        cls.p1 = MonthlyPeriod.objects.create(
            fiscal_year=cls.fy, month=1,
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        cls.p2 = MonthlyPeriod.objects.create(
            fiscal_year=cls.fy, month=2,
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 28))
        cls.p3 = MonthlyPeriod.objects.create(
            fiscal_year=cls.fy, month=3,
            start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
            status="closed")
        cls.dept = Department.objects.create(code="OPS", name="العمليات")
        cls.dept_fin = Department.objects.create(code="FIN", name="المالية")
        cls.dept_dead = Department.objects.create(
            code="OLD", name="إدارة مغلقة", is_active=False)
        cls.cat = ExpenseCategory.objects.create(code="TRAVEL", name="تنقّل")
        cls.acc = Account.objects.create(
            code="5101", name="مصروفات تنقّل", account_type="expense",
            expense_category=cls.cat)
        cls.acc_asset = Account.objects.create(
            code="1100", name="نقدية", account_type="asset")
        cls.acc_dead = Account.objects.create(
            code="5199", name="حساب مغلق", account_type="expense",
            is_active=False)
        cls.sup = Supplier.objects.create(code="SUP-01", name="مؤسسة الإمداد")
        cls.sup2 = Supplier.objects.create(code="SUP-02", name="شركة النور")
        cls.sup_dead = Supplier.objects.create(
            code="SUP-9", name="مورد معطّل", is_active=False)
        # approved budget with a line for (OPS, 5101): Jan 8000
        cls.budget = Budget.objects.create(fiscal_year=cls.fy, name="ميزانية 2026")
        cls.bv = BudgetVersion.objects.create(
            budget=cls.budget, version=1, status="approved")
        line = BudgetLine(
            version=cls.bv, department=cls.dept, account=cls.acc, m01=D_("8000"))
        line.full_clean()
        line.save()
        cls.line = line
        cls.admin = make_user("adm_p6", "admin")
        cls.finance = make_user("fin_p6", "finance")
        cls.auditor = make_user("aud_p6", "auditor")
        cls.mgmt = make_user("mgmt_p6", "management")


def payload(**over):
    data = {
        "expense_number": "",
        "expense_date": "2026-01-15",
        "period": "",            # filled by caller (pk strings)
        "department": "",
        "account": "",
        "expense_category": "",
        "supplier": "",
        "description": "مصروف تدريبي",
        "amount": "1500.00",
        "currency": "USD",
        "payment_method": "transfer",
        "payment_reference": "TR-001",
        "invoice_reference": "",
        "approval_reference": "",
    }
    data.update(over)
    return data


# ================================================================ validation
class ExpenseValidationTests(BaseFixture):
    def _expense(self, **kw):
        defaults = dict(
            expense_number="EXP-2026-90001", expense_date=date(2026, 1, 15),
            period=self.p1, department=self.dept, account=self.acc,
            description="بيان", amount=D_("100"))
        defaults.update(kw)
        return Expense(**defaults)

    def test_date_outside_period_rejected(self):
        e = self._expense(expense_date=date(2026, 2, 10))  # period = January
        with self.assertRaises(ValidationError) as ctx:
            e.full_clean()
        self.assertIn("expense_date", ctx.exception.error_dict)

    def test_non_expense_account_rejected(self):
        e = self._expense(account=self.acc_asset)
        with self.assertRaises(ValidationError) as ctx:
            e.full_clean()
        self.assertIn("account", ctx.exception.error_dict)

    def test_inactive_department_rejected(self):
        e = self._expense(department=self.dept_dead)
        with self.assertRaises(ValidationError) as ctx:
            e.full_clean()
        self.assertIn("department", ctx.exception.error_dict)

    def test_inactive_supplier_rejected(self):
        e = self._expense(supplier=self.sup_dead)
        with self.assertRaises(ValidationError) as ctx:
            e.full_clean()
        self.assertIn("supplier", ctx.exception.error_dict)

    def test_amount_must_be_positive_model_and_db(self):
        e = self._expense(amount=D_("0"))
        with self.assertRaises(ValidationError) as ctx:
            e.full_clean()
        self.assertIn("amount", ctx.exception.error_dict)
        # DB CHECK backstop (bypasses full_clean)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Expense.objects.create(
                    expense_number="EXP-2026-90002",
                    expense_date=date(2026, 1, 10), period=self.p1,
                    department=self.dept, account=self.acc,
                    description="x", amount=D_("0"))

    def test_category_inherits_from_account(self):
        e = self._expense()
        e.full_clean()
        self.assertEqual(e.expense_category_id, self.cat.pk)

    def test_duplicate_control_same_supplier_ref_amount_date(self):
        Expense.objects.create(
            expense_number="EXP-2026-90003", expense_date=date(2026, 1, 10),
            period=self.p1, department=self.dept, account=self.acc,
            supplier=self.sup, invoice_reference="INV-77", description="أ",
            amount=D_("500"))
        dup = self._expense(supplier=self.sup, invoice_reference="INV-77",
                            amount=D_("500"), expense_date=date(2026, 1, 10))
        with self.assertRaises(ValidationError) as ctx:
            dup.full_clean()
        self.assertIn("invoice_reference", ctx.exception.error_dict)

    def test_db_unique_supplier_invoice_reference(self):
        Expense.objects.create(
            expense_number="EXP-2026-90004", expense_date=date(2026, 1, 10),
            period=self.p1, department=self.dept, account=self.acc,
            supplier=self.sup, invoice_reference="INV-88", description="أ",
            amount=D_("500"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Expense.objects.create(
                    expense_number="EXP-2026-90005",
                    expense_date=date(2026, 1, 20), period=self.p1,
                    department=self.dept, account=self.acc,
                    supplier=self.sup, invoice_reference="INV-88",
                    description="ب", amount=D_("900"))

    def test_same_invoice_ref_different_suppliers_ok(self):
        Expense.objects.create(
            expense_number="EXP-2026-90006", expense_date=date(2026, 1, 10),
            period=self.p1, department=self.dept, account=self.acc,
            supplier=self.sup, invoice_reference="INV-1", description="أ",
            amount=D_("500"))
        Expense.objects.create(
            expense_number="EXP-2026-90007", expense_date=date(2026, 1, 11),
            period=self.p1, department=self.dept, account=self.acc,
            supplier=self.sup2, invoice_reference="INV-1", description="ب",
            amount=D_("700"))
        self.assertEqual(Expense.objects.count(), 2)


# ================================================================ services + linkage
class ExpenseServicesTests(BaseFixture):
    def test_number_sequence(self):
        n1 = services.next_expense_number(date(2026, 1, 5))
        self.assertEqual(n1, "EXP-2026-00001")
        Expense.objects.create(
            expense_number=n1, expense_date=date(2026, 1, 5), period=self.p1,
            department=self.dept, account=self.acc, description="أ",
            amount=D_("10"))
        n2 = services.next_expense_number(date(2026, 1, 6))
        self.assertEqual(n2, "EXP-2026-00002")

    def test_period_for_date_helper(self):
        self.assertEqual(services.period_for_date(date(2026, 2, 10)).pk,
                         self.p2.pk)
        self.assertIsNone(services.period_for_date(date(2026, 3, 10)))  # closed

    def test_budget_linkage_budgeted(self):
        e = Expense.objects.create(
            expense_number="EXP-2026-00001", expense_date=date(2026, 1, 15),
            period=self.p1, department=self.dept, account=self.acc,
            description="ضمن الميزانية", amount=D_("1000"))
        ctx = services.expense_budget_context(e)
        self.assertTrue(ctx["budgeted"])
        self.assertEqual(ctx["analysis_version"].pk, self.bv.pk)
        self.assertEqual(ctx["monthly_budget"], D_("8000"))

    def test_budget_linkage_out_of_budget(self):
        e = Expense.objects.create(
            expense_number="EXP-2026-00002", expense_date=date(2026, 1, 16),
            period=self.p1, department=self.dept_fin, account=self.acc,
            description="خارج الميزانية", amount=D_("500"))
        ctx = services.expense_budget_context(e)
        self.assertFalse(ctx["budgeted"])
        self.assertIn("خارج الميزانية", ctx["reason"])


# ================================================================ closed-period rule (HTTP)
class ClosedPeriodHttpTests(BaseFixture):
    def setUp(self):
        self.url = reverse("expenses:create")

    def _c(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_finance_post_to_closed_period_403_and_not_created(self):
        c = self._c(self.finance)
        response = c.post(self.url, payload(
            period=str(self.p3.pk), expense_date="2026-03-15",
            department=str(self.dept.pk), account=str(self.acc.pk),
            amount="700"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertFalse(
            AuditLog.objects.filter(action="closed_period_override").exists())

    def test_admin_post_to_closed_period_allowed_and_audited(self):
        c = self._c(self.admin)
        response = c.post(self.url, payload(
            period=str(self.p3.pk), expense_date="2026-03-15",
            department=str(self.dept.pk), account=str(self.acc.pk),
            amount="700"))
        self.assertEqual(response.status_code, 302)
        e = Expense.objects.get()
        self.assertEqual(e.period_id, self.p3.pk)
        entry = AuditLog.objects.filter(
            action="closed_period_override",
            entity_id=str(self.p3.pk)).first()
        self.assertIsNotNone(entry)
        self.assertIn("مصروف", entry.diff.get("purpose", ""))
        self.assertEqual(entry.actor_label, "adm_p6")

    def test_open_period_no_override_row(self):
        c = self._c(self.finance)
        c.post(self.url, payload(
            period=str(self.p1.pk),
            department=str(self.dept.pk), account=str(self.acc.pk)))
        self.assertEqual(Expense.objects.count(), 1)
        self.assertFalse(
            AuditLog.objects.filter(action="closed_period_override").exists())


# ================================================================ CRUD HTTP + audit
class ExpenseHttpTests(BaseFixture):
    def _c(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("expenses:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_management_denied(self):
        c = self._c(self.mgmt)
        self.assertEqual(c.get(reverse("expenses:list")).status_code, 403)

    def test_auditor_views_but_cannot_create(self):
        c = self._c(self.auditor)
        self.assertEqual(c.get(reverse("expenses:list")).status_code, 200)
        self.assertEqual(c.get(reverse("expenses:create")).status_code, 403)
        response = c.post(reverse("expenses:create"), payload(
            period=str(self.p1.pk),
            department=str(self.dept.pk), account=str(self.acc.pk)))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Expense.objects.count(), 0)

    def test_finance_creates_expense_number_auto_and_audited(self):
        c = self._c(self.finance)
        response = c.post(reverse("expenses:create"), payload(
            period=str(self.p1.pk), department=str(self.dept.pk),
            account=str(self.acc.pk), supplier=str(self.sup.pk),
            invoice_reference="INV-100"))
        self.assertEqual(response.status_code, 302)
        e = Expense.objects.get()
        self.assertEqual(e.expense_number, "EXP-2026-00001")   # auto
        self.assertEqual(e.created_by_id, self.finance.pk)
        self.assertEqual(e.expense_category_id, self.cat.pk)   # inherited
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="expense",
            entity_id=str(e.pk)).exists())

    def test_finance_edits_amount_audited_with_diff(self):
        c = self._c(self.finance)
        e = Expense.objects.create(
            expense_number="EXP-2026-00001", expense_date=date(2026, 1, 15),
            period=self.p1, department=self.dept, account=self.acc,
            description="أ", amount=D_("1000"))
        response = c.post(reverse("expenses:edit", args=[e.pk]), payload(
            period=str(self.p1.pk), department=str(self.dept.pk),
            account=str(self.acc.pk), amount="1250.50"))
        self.assertEqual(response.status_code, 302)
        e.refresh_from_db()
        self.assertEqual(e.amount, D_("1250.50"))
        log = AuditLog.objects.filter(action="entity_updated",
                                      entity_id=str(e.pk)).first()
        self.assertIsNotNone(log)
        self.assertIn("amount", log.diff)
        self.assertEqual(log.diff["amount"]["before"], "1000.00")
        self.assertEqual(log.diff["amount"]["after"], "1250.50")

    def test_duplicate_manual_number_arabic_error(self):
        Expense.objects.create(
            expense_number="EXP-2026-00001", expense_date=date(2026, 1, 15),
            period=self.p1, department=self.dept, account=self.acc,
            description="أ", amount=D_("100"))
        c = self._c(self.finance)
        response = c.post(reverse("expenses:create"), payload(
            expense_number="EXP-2026-00001", period=str(self.p1.pk),
            department=str(self.dept.pk), account=str(self.acc.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مستخدم مسبقًا")

    def test_zero_amount_arabic_error(self):
        c = self._c(self.finance)
        response = c.post(reverse("expenses:create"), payload(
            period=str(self.p1.pk), department=str(self.dept.pk),
            account=str(self.acc.pk), amount="0"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "أكبر من صفر")

    def test_missing_required_fields_arabic(self):
        c = self._c(self.finance)
        data = payload(period=str(self.p1.pk),
                       department=str(self.dept.pk), account=str(self.acc.pk))
        data["description"] = ""
        response = c.post(reverse("expenses:create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "هذا الحقل مطلوب")

    def test_date_outside_period_arabic_form_error(self):
        c = self._c(self.finance)
        response = c.post(reverse("expenses:create"), payload(
            expense_date="2026-02-10", period=str(self.p1.pk),
            department=str(self.dept.pk), account=str(self.acc.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "خارج نطاق الفترة المختارة")

    def test_approval_stamping_and_clearing(self):
        c = self._c(self.finance)
        response = c.post(reverse("expenses:create"), payload(
            period=str(self.p1.pk), department=str(self.dept.pk),
            account=str(self.acc.pk), approval_reference="DEC-2026-01"))
        self.assertEqual(response.status_code, 302)
        e = Expense.objects.get()
        self.assertEqual(e.approved_by_id, self.finance.pk)
        self.assertIsNotNone(e.approved_at)
        # clear on edit
        c.post(reverse("expenses:edit", args=[e.pk]), payload(
            period=str(self.p1.pk), department=str(self.dept.pk),
            account=str(self.acc.pk), approval_reference=""))
        e.refresh_from_db()
        self.assertIsNone(e.approved_by)
        self.assertEqual(e.approval_reference, "")

    def test_detail_shows_budget_linkage(self):
        c = self._c(self.finance)
        e = Expense.objects.create(
            expense_number="EXP-2026-00001", expense_date=date(2026, 1, 15),
            period=self.p1, department=self.dept, account=self.acc,
            description="أ", amount=D_("1000"))
        response = c.get(reverse("expenses:detail", args=[e.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "8000")            # monthly budget from DB
        self.assertContains(response, "المستخدمة في التحليل")


# ================================================================ attachment
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class AttachmentTests(BaseFixture):
    def _c(self, user):
        c = Client()
        c.force_login(user)
        return c

    def _create_with_file(self, user=None):
        c = self._c(user or self.finance)
        fake = SimpleUploadedFile("invoice.txt", b"%PDF-fake-content",
                                  content_type="application/pdf")
        response = c.post(reverse("expenses:create"), payload(
            period=str(self.p1.pk), department=str(self.dept.pk),
            account=str(self.acc.pk), attachment=fake))
        return c, response

    def test_upload_then_view_and_audit(self):
        c, response = self._create_with_file()
        self.assertEqual(response.status_code, 302)
        e = Expense.objects.get()
        self.assertTrue(e.attachment)
        # viewer: auditor has expenses.view
        ca = self._c(self.auditor)
        response = ca.get(reverse("expenses:attachment", args=[e.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content),
                         b"%PDF-fake-content")
        self.assertTrue(AuditLog.objects.filter(
            action="expense_attachment_viewed",
            entity_id=str(e.pk)).exists())

    def test_management_cannot_view_attachment(self):
        _, response = self._create_with_file()
        e = Expense.objects.get()
        cm = self._c(self.mgmt)
        response = cm.get(reverse("expenses:attachment", args=[e.pk]))
        self.assertEqual(response.status_code, 403)

    def test_oversize_attachment_rejected(self):
        c = self._c(self.finance)
        big = SimpleUploadedFile("big.pdf", b"x" * (10 * 1024 * 1024 + 1),
                                 content_type="application/pdf")
        response = c.post(reverse("expenses:create"), payload(
            period=str(self.p1.pk), department=str(self.dept.pk),
            account=str(self.acc.pk), attachment=big))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "10 ميجابايت")
        self.assertEqual(Expense.objects.count(), 0)

    def test_missing_attachment_redirects_with_message(self):
        e = Expense.objects.create(
            expense_number="EXP-2026-00009", expense_date=date(2026, 1, 15),
            period=self.p1, department=self.dept, account=self.acc,
            description="أ", amount=D_("10"))
        c = self._c(self.finance)
        response = c.get(reverse("expenses:attachment", args=[e.pk]))
        self.assertEqual(response.status_code, 302)


# ================================================================ export + search/filter
class ExportSearchFilterTests(BaseFixture):
    def setUp(self):
        self.c = Client()
        self.c.force_login(self.finance)
        for i, (day, dept, amount, cur) in enumerate([
            (5, self.dept, "100.00", "USD"),
            (10, self.dept, "200.00", "USD"),
            (20, self.dept_fin, "300.00", "SAR"),
        ], start=1):
            Expense.objects.create(
                expense_number=f"EXP-2026-0000{i}",
                expense_date=date(2026, 1, day),
                period=self.p1, department=dept, account=self.acc,
                description=f"قيد {i}", amount=D_(amount), currency=cur)

    def test_export_csv_contains_rows_and_headers(self):
        response = self.c.get(reverse("expenses:export"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        body = response.content.decode("utf-8")
        self.assertTrue(body.startswith("﻿"))          # Excel BOM
        self.assertIn("رقم المصروف", body)
        self.assertIn("EXP-2026-00001", body)
        self.assertIn("قيد 3", body)
        self.assertTrue(AuditLog.objects.filter(
            action="expenses_exported").exists())

    def test_csv_formula_text_is_neutralized_and_amount_remains_numeric_text(self):
        expense = Expense.objects.get(expense_number="EXP-2026-00001")
        expense.description = '=HYPERLINK("https://invalid")'
        expense.save(update_fields=["description"])
        response = self.c.get(reverse("expenses:export"))
        body = response.content.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", body)
        self.assertIn(",100.00,", body)

    def test_export_respects_filters(self):
        response = self.c.get(
            reverse("expenses:export"),
            {"department": str(self.dept_fin.pk)})
        body = response.content.decode("utf-8")
        self.assertIn("EXP-2026-00003", body)
        self.assertNotIn("EXP-2026-00001", body)
        log = AuditLog.objects.filter(action="expenses_exported").first()
        self.assertEqual(log.diff.get("count"), 1)

    def test_management_cannot_export(self):
        cm = Client()
        cm.force_login(self.mgmt)
        self.assertEqual(cm.get(reverse("expenses:export")).status_code, 403)

    def test_search_by_number_and_supplier(self):
        url = reverse("expenses:list")
        self.assertEqual(self.c.get(url, {"q": "00002"}).context["total"], 1)
        self.assertEqual(self.c.get(url, {"q": "قيد 3"}).context["total"], 1)

    def test_filters_currency_period_and_date_range(self):
        url = reverse("expenses:list")
        self.assertEqual(
            self.c.get(url, {"currency": "SAR"}).context["total"], 1)
        self.assertEqual(
            self.c.get(url, {"period": str(self.p1.pk)}).context["total"], 3)
        self.assertEqual(
            self.c.get(url, {"date_from": "2026-01-15",
                             "date_to": "2026-01-31"}).context["total"], 1)
        self.assertEqual(
            self.c.get(url, {"department": str(self.dept.pk)}
                       ).context["filtered_total"], D_("300.00"))

    def test_list_pagination(self):
        for i in range(4, 20):
            Expense.objects.create(
                expense_number=f"EXP-2026-{i:05d}",
                expense_date=date(2026, 1, 2), period=self.p1,
                department=self.dept, account=self.acc,
                description=f"إضافي {i}", amount=D_("10"))
        response = self.c.get(reverse("expenses:list"))
        self.assertEqual(len(response.context["rows"]), 15)
        response = self.c.get(reverse("expenses:list"), {"page": 2})
        self.assertEqual(response.context["total"], 19)
