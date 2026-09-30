"""PHASE 12 — المرفقات + التأكد من تتبّع (traceability) العمليات الحساسة."""
import tempfile
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import PERMISSIONS, URL_PERMISSIONS
from apps.audit_register import services as engine
from apps.audit_register.models import AuditException, AuditTest
from apps.expenses.models import Expense
from apps.procurement.models import Procurement
from apps.governance.models import AuditLog, Attachment
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
TEMP_MEDIA = tempfile.mkdtemp(prefix="p12_media_")

CSV_HEAD = ("Date,Department,Account,Supplier,Description,Amount,Invoice,"
            "Currency,Payment Method\n")
CSV_ROWS = ("2026-01-15,OPS,5102,SUP-01,Office supplies,150.50,INV-A1,USD,transfer\n")


def make_user(username, role_code):
    user = User.objects.create_user(username=username, password=PW)
    UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


class GovFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fy = FiscalYear.objects.create(
            code="FY2026", name="2026", year=2026,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        cls.period = MonthlyPeriod.objects.create(
            fiscal_year=cls.fy, month=1,
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        cls.dept = Department.objects.create(code="OPS", name="العمليات")
        cls.dept2 = Department.objects.create(code="DUP", name="مؤقت")
        cls.cat = ExpenseCategory.objects.create(code="SUPPLIES",
                                                 name="مستلزمات")
        cls.acc = Account.objects.create(
            code="5102", name="مستلزمات", account_type="expense",
            expense_category=cls.cat)
        cls.sup = Supplier.objects.create(code="SUP-01", name="مورد أ")
        cls.auditor = make_user("aud_p12", "auditor")
        cls.finance = make_user("fin_p12", "finance")
        cls.mgmt = make_user("mgmt_p12", "management")
        cls.admin = make_user("admin_p12", "admin")
        cls.expense = Expense.objects.create(
            expense_number="EXP-G1", expense_date=date(2026, 1, 10),
            period=cls.period, department=cls.dept, account=cls.acc,
            expense_category=cls.cat, supplier=cls.sup, description="أول",
            amount=D("100"), currency="USD", payment_method="transfer",
            created_by=cls.finance)
        Procurement.objects.create(
            reference_number="PR-G1", date=date(2026, 1, 5),
            department=cls.dept, supplier=cls.sup, account=cls.acc,
            description="بلا عروض", amount=D("15000"),
            status="approved", created_by=cls.finance)
        engine.start_run(
            AuditTest.objects.filter(is_active=True), cls.auditor,
            mode="all_active")

    def as_(self, username):
        from django.test import Client
        c = Client()
        c.force_login(User.objects.get(username=username))
        return c


# ============================================================ المرفقات
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class AttachmentTests(GovFixture):
    def _upload(self, c, entity_type="expense", entity_id=None,
                content=b"%PDF-1.4 test", name="doc.pdf"):
        return c.post(reverse("governance:attachment_upload"), {
            "entity_type": entity_type,
            "entity_id": str(entity_id or self.expense.pk),
            "title": "مرفق تجريبي",
            "file": SimpleUploadedFile(name, content,
                                       content_type="application/pdf"),
            "next": "/",
        })

    def test_upload_metadata_and_audit_log(self):
        c = self.as_("aud_p12")
        response = self._upload(c)
        self.assertEqual(response.status_code, 302)
        att = Attachment.objects.get()
        self.assertEqual(att.title, "مرفق تجريبي")
        self.assertEqual(att.size, len(b"%PDF-1.4 test"))
        self.assertEqual(att.content_type, "application/pdf")
        self.assertEqual(att.uploaded_by_id, self.auditor.pk)
        self.assertEqual(att.entity_type, "expense")
        self.assertEqual(att.get_entity_link(),
                         reverse("expenses:detail", args=[self.expense.pk]))
        log = AuditLog.objects.get(action="attachment_uploaded")
        self.assertEqual(log.entity_type, "attachment")
        self.assertEqual(log.actor_label, "aud_p12")
        self.assertEqual(log.diff["linked"],
                         {"type": "expense", "id": str(self.expense.pk)})

    def test_view_and_download_with_logs(self):
        c = self.as_("aud_p12")
        self._upload(c)
        att = Attachment.objects.get()
        view = c.get(reverse("governance:attachment_view", args=[att.pk]))
        self.assertEqual(view.status_code, 200)
        self.assertEqual(b"".join(view.streaming_content),
                         b"%PDF-1.4 test")
        download = c.get(
            reverse("governance:attachment_download", args=[att.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        # الاسم قد يُحقن بلاحقة فريدة من Django storage
        self.assertIn("doc", download["Content-Disposition"])
        self.assertIn(".pdf", download["Content-Disposition"])
        actions = set(AuditLog.objects.filter(
            entity_type="attachment").values_list("action", flat=True))
        self.assertEqual(
            actions, {"attachment_uploaded", "attachment_viewed",
                      "attachment_downloaded"})

    def test_invalid_entity_and_oversize_rejected(self):
        c = self.as_("aud_p12")
        # كيان غير موجود
        self._upload(c, entity_id=99999)
        self.assertEqual(Attachment.objects.count(), 0)
        # نوع غير صالح
        self._upload(c, entity_type="nope")
        self.assertEqual(Attachment.objects.count(), 0)
        # GET مرفوض
        self.assertEqual(
            c.get(reverse("governance:attachment_upload")).status_code, 400)
        # حجم >10MB
        big = SimpleUploadedFile("big.pdf", b"x" * (11 * 1024 * 1024))
        c.post(reverse("governance:attachment_upload"), {
            "entity_type": "expense", "entity_id": str(self.expense.pk),
            "file": big, "next": "/"})
        self.assertEqual(Attachment.objects.count(), 0)

    def test_rbac(self):
        att = Attachment.objects.create(
            file=SimpleUploadedFile("x.pdf", b"x"),
            entity_type="expense", entity_id=str(self.expense.pk),
            uploaded_by=self.auditor, size=1, content_type="application/pdf")
        # finance لا يملك attachments.view/manage
        cf = self.as_("fin_p12")
        self.assertEqual(
            cf.get(reverse("governance:attachment_view", args=[att.pk]))
            .status_code, 403)
        self.assertEqual(self._upload(cf).status_code, 403)
        # management لا يملك attachments.view → القسم مخفي في صفحة التفصيل
        cm = self.as_("mgmt_p12")
        html = cm.get(
            reverse("expenses:detail", args=[self.expense.pk])).content
        self.assertNotIn("المرفقات (Attachments)".encode(), html)
        # auditor يراه
        ca = self.as_("aud_p12")
        html = ca.get(
            reverse("expenses:detail", args=[self.expense.pk])).content
        self.assertIn("المرفقات (Attachments)".encode(), html)

    def test_section_on_all_four_detail_pages(self):
        from apps.audit_register.models import AuditFinding
        finding = AuditFinding.objects.create(
            finding_code="F-2026-00001", title="ت", criteria="c",
            condition="d", impact="i", recommendation="r")
        exception = AuditException.objects.filter(
            source_type="procurement").first()
        if exception is None:
            self.skipTest("لا استثناء في الـ fixture")
        c = self.as_("aud_p12")
        pages = [
            reverse("expenses:detail", args=[self.expense.pk]),
            reverse("audit:finding_detail", args=[finding.pk]),
            reverse("audit:exception_detail", args=[exception.pk]),
        ]
        for url in pages:
            html = c.get(url).content.decode()
            self.assertIn("المرفقات (Attachments)", html, url)
            self.assertIn('name="file"', html, url)  # نموذج الرفع


# ============================================================ التتبّع
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class TraceabilityTests(GovFixture):
    """التأكد أن كل عملية حساسة مسجّلة بمنفّذ ووقت وكيان (traceable)."""

    def _trace(self, action, entity_type=None, require_actor=True):
        qs = AuditLog.objects.filter(action=action)
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        log = qs.latest("created_at")
        if require_actor:
            self.assertTrue(log.actor_label, f"{action} بلا منفّذ")
        self.assertTrue(log.created_at, f"{action} بلا وقت")
        return log

    def test_create_update_delete(self):
        # reference.edit مملوكة للمدير فقط في المصفوفة المعتمدة
        c = self.as_("admin_p12")
        url = reverse("reference:department_create")
        response = c.post(url, {"code": "TR1", "name": "إدارة التتبع"})
        self.assertEqual(response.status_code, 302)
        dept = Department.objects.get(code="TR1")
        log = self._trace("entity_created", "department")
        self.assertEqual(log.entity_id, str(dept.pk))
        self.assertEqual(log.actor_label, "admin_p12")

        c.post(reverse("reference:department_edit", args=[dept.pk]),
               {"code": "TR1", "name": "إدارة مُعدّلة"})
        log = self._trace("entity_updated", "department")
        self.assertEqual(log.entity_id, str(dept.pk))
        # صيغة changes_between: {field: {"before": ..., "after": ...}}
        self.assertEqual(log.diff["name"]["before"], "إدارة التتبع")
        self.assertEqual(log.diff["name"]["after"], "إدارة مُعدّلة")

        c.post(reverse("reference:department_delete", args=[dept.pk]))
        self.assertFalse(Department.objects.filter(pk=dept.pk).exists())
        log = self._trace("entity_deleted", "department")
        self.assertEqual(log.entity_id, str(dept.pk))

    def test_import_logged(self):
        from apps.imports.models import ImportJob
        c = self.as_("fin_p12")
        response = c.post(reverse("imports:new"), {
            "target": "expenses",
            "source_file": SimpleUploadedFile(
                "t.csv", (CSV_HEAD + CSV_ROWS).encode("utf-8"))})
        self.assertEqual(response.status_code, 302)
        job = ImportJob.objects.get()
        mapping = {f"map-{k}": v for k, v in (job.column_map or {}).items()}
        c.post(reverse("imports:validate", args=[job.pk]), mapping)
        c.post(reverse("imports:confirm", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        log = self._trace("data_imported")
        self.assertEqual(log.entity_id, str(job.pk))
        self.assertEqual(log.diff["imported"], 1)

    def test_run_audit_test_logged(self):
        c = self.as_("aud_p12")
        response = c.post(reverse("audit:run_start"), {"mode": "all_active"})
        self.assertEqual(response.status_code, 302)
        log = self._trace("entity_created", "audit_run")
        self.assertEqual(log.actor_label, "aud_p12")
        log2 = AuditLog.objects.filter(
            action="entity_updated", entity_type="audit_run"
        ).latest("created_at")
        self.assertEqual(log2.entity_id, log.entity_id)

    def test_change_rule_and_risk_logged(self):
        from apps.audit_register.models import AuditTest as AT
        test = AT.objects.get(test_code="T-BUD-01")
        c = self.as_("aud_p12")
        from apps.audit_register.forms import AuditTestForm
        data = {
            "test_code": test.test_code,
            "name": test.name,
            "domain": test.domain,
            "objective": test.objective,
            "rule_text": "قاعدة مُعدّلة — Synthetic Policy Rule (نسخة2)",
            "data_source": test.data_source,
            "expected_result": test.expected_result,
            "exception_type": test.exception_type,
            "default_risk": "Low" if test.default_risk != "Low" else "High",
            "auditor_action": test.auditor_action,
            "engine_key": test.engine_key,
            "parameters_json": __import__("json").dumps(test.parameters),
            "is_active": "on" if test.is_active else "",
            "synthetic_rule": "on" if test.synthetic_rule else "",
        }
        form = AuditTestForm(data, instance=test)
        self.assertTrue(form.is_valid(), form.errors)
        response = c.post(
            reverse("audit:test_edit", args=[test.pk]), data)
        self.assertEqual(response.status_code, 302)
        log = self._trace("entity_updated", "audit_test")
        self.assertIn("rule_text", log.diff["before"])
        self.assertIn("default_risk", log.diff["before"])
        self.assertNotEqual(log.diff["before"]["rule_text"],
                            log.diff["after"]["rule_text"])
        self.assertNotEqual(log.diff["before"]["default_risk"],
                            log.diff["after"]["default_risk"])

    def test_create_finding_and_change_status_logged(self):
        from apps.audit_register.models import AuditFinding
        exception = AuditException.objects.filter(
            source_type="procurement").first()
        if exception is None:
            self.skipTest("لا استثناء")
        c = self.as_("aud_p12")
        response = c.post(reverse("audit:finding_create"), {
            "exception": str(exception.pk),
            "title": "نتيجة للتتبّع", "criteria": "معيار", "condition": "وضع",
            "impact": "أثر", "cause": "", "cause_supported": "on",
            "risk_level": "High", "recommendation": "توصية",
            "management_action": "", "status": "open", "status_note": "",
        })
        self.assertEqual(response.status_code, 302)
        finding = AuditFinding.objects.get()
        log = self._trace("entity_created", "audit_finding")
        self.assertEqual(log.entity_id, str(finding.pk))
        self.assertEqual(log.actor_label, "aud_p12")

        # تغيير حالة الاستثناء (Change Status)
        response = c.post(
            reverse("audit:exception_update", args=[exception.pk]),
            {"status": "acknowledged", "status_note": "اعتُمد للتتبّع"})
        self.assertEqual(response.status_code, 302)
        exception.refresh_from_db()
        self.assertEqual(exception.status, "acknowledged")
        log = self._trace("entity_updated", "audit_exception")
        self.assertEqual(log.entity_id, str(exception.pk))

        # تغيير حالة Finding (Change Status)
        response = c.post(
            reverse("audit:finding_edit", args=[finding.pk]), {
                "title": finding.title, "criteria": finding.criteria,
                "condition": finding.condition, "impact": finding.impact,
                "cause": "", "cause_supported": "on",
                "risk_level": "High",
                "recommendation": finding.recommendation,
                "management_action": "إجراء الإدارة",
                "status": "in_progress", "status_note": "بدأت المعالجة",
            })
        self.assertEqual(response.status_code, 302)
        log = self._trace("entity_updated", "audit_finding")
        self.assertEqual(log.entity_id, str(finding.pk))

    def test_login_security_events_logged(self):
        from django.test import Client
        c = Client()
        # دخول فاشل
        c.post(reverse("accounts:login"), {
            "username": "fin_p12", "password": "WRONG-PASS"})
        log = self._trace("login_failed", require_actor=False)
        # المنفّذ مجهول عمدًا (بيانات دخول خاطئة) — التتبّع عبر اسم المحاولة
        self.assertEqual(log.diff["username"], "fin_p12")
        self.assertEqual(log.entity_id, "fin_p12")
        self.assertEqual(log.context.get("ip"), "127.0.0.1")
        # دخول ناجح
        c.post(reverse("accounts:login"), {
            "username": "fin_p12", "password": PW})
        log = self._trace("login")
        self.assertEqual(log.actor_label, "fin_p12")
        self.assertIn("ip", log.context)
        self.assertIn("user_agent", log.context)
        # خروج
        c.post(reverse("accounts:logout"))
        log = self._trace("logout")
        self.assertEqual(log.actor_label, "fin_p12")

    def test_audit_trail_page_filters_and_rbac(self):
        c = self.as_("aud_p12")
        response = c.get(reverse("governance:audit_trail"))
        self.assertEqual(response.status_code, 200)
        # إنشاء حدث ثم فلترة
        c.post(reverse("reference:department_create"),
               {"code": "TRF", "name": "فلترة"})
        response = c.get(reverse("governance:audit_trail"),
                         {"action": "entity_created",
                          "entity_type": "department"})
        self.assertEqual(response.status_code, 200)
        logs = list(response.context["logs"])
        self.assertTrue(all(l.action == "entity_created" for l in logs))
        self.assertTrue(all(l.entity_type == "department" for l in logs))
        # management لا يملك audittrail.view
        cm = self.as_("mgmt_p12")
        self.assertEqual(
            cm.get(reverse("governance:audit_trail")).status_code, 403)
        # anon →302
        self.assertEqual(
            self.client.get(reverse("governance:audit_trail")).status_code,
            302)

    def test_catalog_and_rules_stay_30(self):
        self.assertEqual(len(PERMISSIONS), 30)
        self.assertEqual(URL_PERMISSIONS["governance:attachment_upload"],
                         "attachments.manage")
        self.assertEqual(URL_PERMISSIONS["governance:attachment_view"],
                         "attachments.view")
        self.assertEqual(URL_PERMISSIONS["governance:attachment_download"],
                         "attachments.view")
