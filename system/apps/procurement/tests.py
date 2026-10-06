"""PHASE 7 — Procurement: CRUD, relationships/quotations, audit-test facts,
HTTP permissions — all real responses.
"""
from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal as D

D_ = D  # alias used in fixtures

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.governance.models import AuditLog
from apps.procurement import services
from apps.procurement.models import Procurement, Quotation
from apps.reference.models import (
    Account,
    Department,
    ExpenseCategory,
    FiscalYear,
    Supplier,
)

User = get_user_model()
PW = "S3cure-Demo-Pass!"
TEMP_MEDIA = tempfile.mkdtemp(prefix="p7_media_")


def make_user(username, role_code):
    user = User.objects.create_user(username=username, password=PW)
    UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


class BaseFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fy = FiscalYear.objects.create(
            code="FY2026", name="السنة 2026", year=2026,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        cls.dept = Department.objects.create(code="OPS", name="العمليات")
        cls.dept_dead = Department.objects.create(
            code="OLD", name="معطّلة", is_active=False)
        cls.cat = ExpenseCategory.objects.create(code="SUPPLIES", name="مستلزمات")
        cls.acc = Account.objects.create(
            code="5102", name="مستلزمات مكتبية", account_type="expense",
            expense_category=cls.cat)
        cls.analytical_acc = Account.objects.create(
            code="510201", name="قرطاسية", account_type="expense",
            level=6, ledger_type="sub", parent=cls.acc,
            expense_category=cls.cat,
        )
        cls.other_main_acc = Account.objects.create(
            code="5202", name="مصروفات أخرى", account_type="expense")
        cls.other_analytical_acc = Account.objects.create(
            code="520201", name="تحليلي آخر", account_type="expense",
            level=6, ledger_type="sub", parent=cls.other_main_acc,
        )
        cls.acc_asset = Account.objects.create(
            code="1100", name="نقدية", account_type="asset")
        cls.sup = Supplier.objects.create(code="SUP-01", name="مؤسسة الإمداد")
        cls.sup2 = Supplier.objects.create(code="SUP-02", name="شركة النور")
        cls.sup_dead = Supplier.objects.create(
            code="SUP-9", name="مورد معطّل", is_active=False)
        cls.admin = make_user("adm_p7", "admin")
        cls.finance = make_user("fin_p7", "finance")
        cls.auditor = make_user("aud_p7", "auditor")
        cls.mgmt = make_user("mgmt_p7", "management")

    def make_record(self, **kw):
        defaults = dict(
            reference_number="PR-2026-00001", date=date(2026, 2, 1),
            department=self.dept, supplier=self.sup, account=self.acc,
            description="شراء مستلزمات مكتبية", amount=D_("4500"),
        )
        defaults.update(kw)
        return Procurement.objects.create(**defaults)


def payload(**over):
    data = {
        "reference_number": "",
        "date": "2026-02-10",
        "department": "",
        "supplier": "",
        "account": "",
        "expense_category": "",
        "description": "ترسية شراء أجهزة",
        "amount": "12000.00",
        "status": "draft",
        "purchase_order": "",
        "approval_reference": "",
        "payment_method": "transfer",
        "payment_reference": "",
        "notes": "",
    }
    data.update(over)
    return data


# ================================================================ model validation
class ProcurementValidationTests(BaseFixture):
    def test_analytical_account_must_be_level_six_child_of_main(self):
        valid = Procurement(
            reference_number="PR-AN-1", date=date(2026, 2, 1),
            department=self.dept, supplier=self.sup, account=self.acc,
            analytical_account=self.analytical_acc,
            description="x", amount=D_("100"),
        )
        valid.full_clean()
        invalid = Procurement(
            reference_number="PR-AN-2", date=date(2026, 2, 1),
            department=self.dept, supplier=self.sup, account=self.acc,
            analytical_account=self.other_analytical_acc,
            description="x", amount=D_("100"),
        )
        with self.assertRaises(ValidationError) as ctx:
            invalid.full_clean()
        self.assertIn("analytical_account", ctx.exception.error_dict)

    def test_amount_positive_model_and_db(self):
        p = Procurement(
            reference_number="PR-X1", date=date(2026, 2, 1),
            department=self.dept, supplier=self.sup, account=self.acc,
            description="x", amount=D_("0"))
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("amount", ctx.exception.error_dict)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Procurement.objects.create(
                    reference_number="PR-X2", date=date(2026, 2, 1),
                    department=self.dept, supplier=self.sup, account=self.acc,
                    description="x", amount=D_("0"))

    def test_non_expense_account_rejected(self):
        p = Procurement(reference_number="PR-X3", date=date(2026, 2, 1),
                        department=self.dept, supplier=self.sup,
                        account=self.acc_asset, description="x",
                        amount=D_("100"))
        with self.assertRaises(ValidationError) as ctx:
            p.full_clean()
        self.assertIn("account", ctx.exception.error_dict)

    def test_inactive_dimensions_rejected(self):
        for field, value in (("department", self.dept_dead),
                             ("supplier", self.sup_dead)):
            kwargs = dict(
                reference_number=f"PR-{field}", date=date(2026, 2, 1),
                department=self.dept, supplier=self.sup,
                account=self.acc, description="x", amount=D_("100"))
            kwargs[field] = value
            p = Procurement(**kwargs)
            with self.assertRaises(ValidationError) as ctx:
                p.full_clean()
            self.assertIn(field, ctx.exception.error_dict)

    def test_category_inherits_from_account(self):
        p = Procurement(reference_number="PR-X4", date=date(2026, 2, 1),
                        department=self.dept, supplier=self.sup,
                        account=self.acc, description="x", amount=D_("100"))
        p.full_clean()
        self.assertEqual(p.expense_category_id, self.cat.pk)

    def test_quote_amount_positive_and_unique_per_supplier(self):
        p = self.make_record()
        Quotation.objects.create(procurement=p, supplier=self.sup,
                                 amount=D_("4000"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Quotation.objects.create(procurement=p, supplier=self.sup,
                                         amount=D_("3900"))
        bad = Quotation(procurement=p, supplier=self.sup2, amount=D_("0"))
        with self.assertRaises(ValidationError):
            bad.full_clean()


# ================================================================ relationships
class ProcurementRelationTests(BaseFixture):
    def test_protected_supplier_department_account(self):
        p = self.make_record()
        for obj in (self.sup, self.dept, self.acc):
            with self.assertRaises(ProtectedError):
                obj.delete()
        self.assertTrue(Procurement.objects.filter(pk=p.pk).exists())

    def test_quotes_cascade_with_procurement(self):
        p = self.make_record()
        Quotation.objects.create(procurement=p, supplier=self.sup2,
                                 amount=D_("4100"))
        p.delete()
        self.assertEqual(Quotation.objects.count(), 0)

    def test_quote_supplier_protected(self):
        p = self.make_record()
        q = Quotation.objects.create(procurement=p, supplier=self.sup2,
                                     amount=D_("4100"))
        with self.assertRaises(ProtectedError):
            self.sup2.delete()
        self.assertTrue(Quotation.objects.filter(pk=q.pk).exists())


# ================================================================ services
class ProcurementServicesTests(BaseFixture):
    def test_number_sequence(self):
        n1 = services.next_procurement_number(date(2026, 2, 1))
        self.assertEqual(n1, "PR-2026-00001")
        self.make_record()
        n2 = services.next_procurement_number(date(2026, 2, 2))
        self.assertEqual(n2, "PR-2026-00002")

    def test_audit_context_facts(self):
        p = self.make_record()          # no PO, no approval, no quotes
        ctx = services.procurement_audit_context(p)
        self.assertFalse(ctx["has_po"])
        self.assertFalse(ctx["has_approval"])
        self.assertEqual(ctx["quote_count"], 0)
        self.assertIsNone(ctx["lowest_quote"])
        self.assertFalse(ctx["has_attachment"])
        self.assertEqual(ctx["supplier"]["code"], "SUP-01")
        self.assertEqual(ctx["amount"], D_("4500"))
        # enrich
        p.purchase_order = "PO-2026-014"
        p.approval_reference = "DEC-07"
        p.save()
        Quotation.objects.create(procurement=p, supplier=self.sup,
                                 amount=D_("4600"))
        Quotation.objects.create(procurement=p, supplier=self.sup2,
                                 amount=D_("4300"))
        ctx = services.procurement_audit_context(p)
        self.assertTrue(ctx["has_po"])
        self.assertTrue(ctx["has_approval"])
        self.assertEqual(ctx["quote_count"], 2)
        self.assertEqual(ctx["lowest_quote"], D_("4300"))


# ================================================================ HTTP CRUD
class ProcurementHttpTests(BaseFixture):
    def _c(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("procurement:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_management_denied(self):
        self.assertEqual(
            self._c(self.mgmt).get(reverse("procurement:list")).status_code, 403)

    def test_auditor_view_only(self):
        c = self._c(self.auditor)
        self.assertEqual(c.get(reverse("procurement:list")).status_code, 200)
        self.assertEqual(c.get(reverse("procurement:create")).status_code, 403)
        response = c.post(reverse("procurement:create"), payload(
            department=str(self.dept.pk), supplier=str(self.sup.pk),
            account=str(self.acc.pk)))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Procurement.objects.count(), 0)

    def test_finance_create_full_record_audited(self):
        c = self._c(self.finance)
        response = c.post(reverse("procurement:create"), payload(
            department=str(self.dept.pk), supplier=str(self.sup.pk),
            account=str(self.acc.pk), purchase_order="PO-77",
            approval_reference="DEC-2026-03"))
        self.assertEqual(response.status_code, 302)
        p = Procurement.objects.get()
        self.assertEqual(p.reference_number, "PR-2026-00001")   # auto
        self.assertEqual(p.created_by_id, self.finance.pk)
        self.assertEqual(p.expense_category_id, self.cat.pk)    # inherited
        self.assertTrue(p.has_approval)
        self.assertIsNotNone(p.approved_by)
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="procurement",
            entity_id=str(p.pk)).exists())

    def test_edit_status_and_amount_audited_with_diff(self):
        c = self._c(self.finance)
        p = self.make_record()
        response = c.post(reverse("procurement:edit", args=[p.pk]), payload(
            reference_number=p.reference_number,
            department=str(self.dept.pk), supplier=str(self.sup.pk),
            account=str(self.acc.pk), amount="5000",
            status="approved", approval_reference="DEC-1"))
        self.assertEqual(response.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.amount, D_("5000"))
        self.assertEqual(p.status, "approved")
        log = AuditLog.objects.filter(action="entity_updated",
                                      entity_id=str(p.pk)).first()
        self.assertIsNotNone(log)
        self.assertIn("amount", log.diff)
        self.assertIn("status", log.diff)

    def test_delete_draft_ok_and_audited(self):
        c = self._c(self.admin)
        p = self.make_record()
        response = c.post(reverse("procurement:delete", args=[p.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Procurement.objects.filter(pk=p.pk).exists())
        self.assertTrue(AuditLog.objects.filter(
            action="entity_deleted", entity_type="procurement",
            entity_id=str(p.pk)).exists())

    def test_delete_non_draft_refused(self):
        c = self._c(self.admin)
        p = self.make_record(status="approved")
        response = c.post(reverse("procurement:delete", args=[p.pk]))
        self.assertEqual(response.status_code, 302)   # redirect with error
        self.assertTrue(Procurement.objects.filter(pk=p.pk).exists())


# ================================================================ quotations HTTP
class QuotationHttpTests(BaseFixture):
    def _c(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_quote_lifecycle_audited(self):
        p = self.make_record()
        c = self._c(self.finance)
        # create quote 1 (supplier)
        response = c.post(reverse("procurement:quote_create", args=[p.pk]),
                          {"supplier": str(self.sup.pk), "amount": "4600",
                           "reference": "Q-01"})
        self.assertEqual(response.status_code, 302)
        # create quote 2 (supplier2)
        c.post(reverse("procurement:quote_create", args=[p.pk]),
               {"supplier": str(self.sup2.pk), "amount": "4300",
                "reference": "Q-02"})
        self.assertEqual(p.quotations.count(), 2)
        self.assertEqual(
            AuditLog.objects.filter(action="entity_created",
                                    entity_type="quotation").count(), 2)
        # duplicate supplier quote rejected (Arabic)
        response = c.post(reverse("procurement:quote_create", args=[p.pk]),
                          {"supplier": str(self.sup.pk), "amount": "4500"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "عرض واحد لكل مورّد")
        self.assertEqual(p.quotations.count(), 2)
        # edit + delete
        q = p.quotations.get(supplier=self.sup2)
        response = c.post(reverse("procurement:quote_edit", args=[q.pk]),
                          {"supplier": str(self.sup2.pk), "amount": "4200"})
        self.assertEqual(response.status_code, 302)
        q.refresh_from_db()
        self.assertEqual(q.amount, D_("4200"))
        self.assertTrue(AuditLog.objects.filter(
            action="entity_updated", entity_type="quotation",
            entity_id=str(q.pk)).exists())
        response = c.post(reverse("procurement:quote_delete", args=[q.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(p.quotations.count(), 1)
        self.assertTrue(AuditLog.objects.filter(
            action="entity_deleted", entity_type="quotation",
            entity_id=str(q.pk)).exists())

    def test_auditor_cannot_mutate_quotes(self):
        p = self.make_record()
        c = self._c(self.auditor)
        response = c.post(reverse("procurement:quote_create", args=[p.pk]),
                          {"supplier": str(self.sup.pk), "amount": "4600"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(p.quotations.count(), 0)


# ================================================================ attachment
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class AttachmentTests(BaseFixture):
    def _c(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_upload_view_and_audit(self):
        c = self._c(self.finance)
        fake = SimpleUploadedFile("po.txt", b"PO-CONTENT",
                                  content_type="application/pdf")
        response = c.post(reverse("procurement:create"), payload(
            department=str(self.dept.pk), supplier=str(self.sup.pk),
            account=str(self.acc.pk), attachment=fake))
        self.assertEqual(response.status_code, 302)
        p = Procurement.objects.get()
        self.assertTrue(p.attachment)
        ca = self._c(self.auditor)
        response = ca.get(reverse("procurement:attachment", args=[p.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"PO-CONTENT")
        self.assertTrue(AuditLog.objects.filter(
            action="procurement_attachment_viewed",
            entity_id=str(p.pk)).exists())
        # management denied
        cm = self._c(self.mgmt)
        self.assertEqual(
            cm.get(reverse("procurement:attachment", args=[p.pk])).status_code,
            403)


# ================================================================ search/filter
class SearchFilterTests(BaseFixture):
    def setUp(self):
        self.c = Client()
        self.c.force_login(self.finance)
        self.p1 = self.make_record()                       # draft, no PO
        self.p2 = self.make_record(
            reference_number="PR-2026-00002", date=date(2026, 3, 5),
            department=self.dept_fin if hasattr(self, "dept_fin")
            else Department.objects.create(code="FIN2", name="المالية"),
            supplier=self.sup2, status="approved",
            purchase_order="PO-9", approval_reference="DEC-9",
            amount=D_("9000"))

    def test_search_by_po_and_number(self):
        url = reverse("procurement:list")
        self.assertEqual(self.c.get(url, {"q": "PO-9"}).context["total"], 1)
        self.assertEqual(
            self.c.get(url, {"q": "PR-2026-00001"}).context["total"], 1)

    def test_filters_status_po_approval_date(self):
        url = reverse("procurement:list")
        self.assertEqual(self.c.get(url, {"status": "approved"}
                                    ).context["total"], 1)
        self.assertEqual(self.c.get(url, {"has_po": "yes"}
                                    ).context["total"], 1)
        self.assertEqual(self.c.get(url, {"has_po": "no"}
                                    ).context["total"], 1)
        self.assertEqual(self.c.get(url, {"has_approval": "no"}
                                    ).context["total"], 1)
        self.assertEqual(self.c.get(url, {"date_from": "2026-03-01"}
                                    ).context["total"], 1)
        self.assertEqual(
            self.c.get(url, {"supplier": str(self.sup.pk)}
                       ).context["filtered_total"], D_("4500"))

    def test_detail_shows_audit_context(self):
        Quotation.objects.create(procurement=self.p1, supplier=self.sup,
                                 amount=D_("4400"))
        response = self.c.get(reverse("procurement:detail", args=[self.p1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "حقائق اختبارات الرقابة")
        self.assertContains(response, "4400")
        self.assertContains(response, "بدون PO")
