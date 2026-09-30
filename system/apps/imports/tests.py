"""PHASE 8 — Import Pipeline tests: extraction (CSV/xlsx/PDF), mapping,
validation matrix, duplicates, confirmation, RBAC, logs — Synthetic only.
"""
from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import PERMISSIONS, URL_PERMISSIONS, ALL_CODES
from apps.expenses.models import Expense
from apps.governance.models import AuditLog
from apps.imports import services as svc
from apps.imports.models import ImportJob
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
TEMP_MEDIA = tempfile.mkdtemp(prefix="p8_media_")

CSV_HEAD = ("Date,Department,Account,Supplier,Description,Amount,Invoice,"
            "Currency,Payment Method\n")
CSV_ROWS = (
    "2026-01-15,OPS,5102,SUP-01,Office supplies,150.50,INV-A1,USD,transfer\n"
    "2026-02-10,FINANCE,5210,SUP-02,Taxi trips,75,INV-A2,USD,cash\n")


def make_user(username, role_code):
    user = User.objects.create_user(username=username, password=PW)
    UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


def minimal_pdf(lines: list[str]) -> bytes:
    """Hand-built single-page PDF with Helvetica text (ASCII lines)."""
    content = "BT /F1 10 Tf 12 TL 40 760 Td\n"
    for line in lines:
        esc = (line.replace("\\", r"\\").replace("(", r"\(")
               .replace(")", r"\)"))
        content += f"({esc}) Tj\nT*\n"
    content += "ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
         "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"),
        (f"<< /Length {len(content)} >>\nstream\n{content}\nendstream"),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref_off = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_off}\n%%EOF").encode()
    return bytes(out)


class BaseFixture(TestCase):
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
        cls.p_mar = MonthlyPeriod.objects.create(
            fiscal_year=cls.fy, month=3, start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31), status="closed")
        cls.dept = Department.objects.create(code="OPS", name="العمليات")
        cls.dept_fin = Department.objects.create(code="FINANCE", name="المالية")
        cls.dept_dead = Department.objects.create(
            code="OLD", name="معطّلة", is_active=False)
        cls.cat = ExpenseCategory.objects.create(code="SUPPLIES", name="مستلزمات")
        cls.acc = Account.objects.create(
            code="5102", name="مستلزمات مكتبية", account_type="expense",
            expense_category=cls.cat)
        cls.acc2 = Account.objects.create(
            code="5210", name="سفر", account_type="expense",
            expense_category=cls.cat)
        cls.acc_asset = Account.objects.create(
            code="1100", name="نقدية", account_type="asset")
        cls.sup1 = Supplier.objects.create(code="SUP-01", name="مؤسسة الإمداد")
        cls.sup2 = Supplier.objects.create(code="SUP-02", name="شركة النور")
        cls.sup_dead = Supplier.objects.create(
            code="SUP-9", name="معطّل", is_active=False)
        cls.finance = make_user("fin_p8", "finance")
        cls.admin = make_user("adm_p8", "admin")
        cls.auditor = make_user("aud_p8", "auditor")
        cls.mgmt = make_user("mgmt_p8", "management")

    def make_job(self, name="data.csv", content=b"", fmt="csv", user=None):
        upload = SimpleUploadedFile(name, content,
                                    content_type="text/csv")
        job = ImportJob.objects.create(
            target="expenses",
            source_file=upload,
            original_filename=name,
            file_format=fmt,
            created_by=user or self.finance,
        )
        job.log("uploaded", filename=name, fmt=fmt, size_bytes=upload.size)
        job.save(update_fields=["job_log", "updated_at"])
        return job

    def extract(self, name, content, fmt="csv", user=None):
        job = self.make_job(name, content, fmt, user)
        svc.extract_job(job)
        job.refresh_from_db()
        return job


# ================================================================ extraction
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ExtractTests(BaseFixture):
    def test_csv_utf8_bom_and_suggestions(self):
        job = self.extract("t.csv", (CSV_HEAD + CSV_ROWS).encode("utf-8-sig"))
        self.assertEqual(job.status, "extracted")
        self.assertEqual(len(job.rows), 2)
        self.assertIn("Description", job.headers)
        self.assertEqual(job.column_map.get("expense_date"), "Date")
        self.assertEqual(job.column_map.get("amount"), "Amount")
        self.assertEqual(job.column_map.get("payment_method"), "Payment Method")
        events = [e["event"] for e in job.job_log]
        self.assertIn("uploaded", events)
        self.assertIn("extract_completed", events)

    def test_csv_semicolon_separator(self):
        content = ("Date;Department;Account;Description;Amount\n"
                   "2026-01-05;OPS;5102;desc;10\n").encode("utf-8")
        job = self.extract("s.csv", content)
        self.assertEqual(job.headers,
                         ["Date", "Department", "Account", "Description",
                          "Amount"])
        self.assertEqual(job.rows[0]["source"]["Amount"], "10")

    def test_csv_cp1256_arabic_preserved(self):
        content = ("Date,Department,Account,Description,Amount\n"
                   "2026-01-05,OPS,5102,شراء قهوة للضيوف,45\n").encode("cp1256")
        job = self.extract("ar.csv", content)
        self.assertEqual(job.rows[0]["source"]["Description"],
                         "شراء قهوة للضيوف")

    def test_xlsx_extraction(self):
        from io import BytesIO
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["Date", "Department", "Account", "Description", "Amount"])
        ws.append(["2026-01-05", "OPS", "5102", "printer toner", 450])
        ws.append(["2026-02-03", "FINANCE", "5210", "travel", 120.5])
        buf = BytesIO()
        wb.save(buf)
        job = self.extract("t.xlsx", buf.getvalue(), fmt="xlsx")
        self.assertEqual(job.status, "extracted")
        self.assertEqual(len(job.rows), 2)
        self.assertEqual(job.rows[0]["source"]["Description"], "printer toner")

    def test_pdf_pipe_table_flow(self):
        lines = [
            "Date|Department|Account|Description|Amount",
            "2026-01-05|OPS|5102|Paper reams|88",
            "2026-02-12|FINANCE|5210|Client lunch|46.75",
        ]
        job = self.extract("t.pdf", minimal_pdf(lines), fmt="pdf")
        self.assertEqual(job.status, "extracted")
        self.assertEqual(job.headers[0], "Date")
        self.assertEqual(len(job.rows), 2)
        self.assertEqual(job.rows[0]["source"]["Amount"], "88")

    def test_pdf_empty_mentions_optional_ocr(self):
        job = self.extract("blank.pdf", minimal_pdf([""]), fmt="pdf")
        self.assertEqual(job.status, "extracted")
        self.assertEqual(job.rows, [])
        blob = " ".join(job.extraction_warnings)
        self.assertIn("OCR", blob)
        self.assertIn("اختيارية", blob)

    def test_unsupported_extension_rejected(self):
        from apps.imports.forms import ImportUploadForm
        form = ImportUploadForm(
            data={"target": "expenses"},
            files={"source_file": SimpleUploadedFile("x.txt", b"a,b")})
        self.assertFalse(form.is_valid())
        self.assertIn("صيغة الملف غير مدعومة",
                      str(form.errors["source_file"]))

    def test_oversize_file_rejected(self):
        from apps.imports.forms import ImportUploadForm
        big = SimpleUploadedFile("big.csv", b"x" * (
            svc.MAX_FILE_MB * 1024 * 1024 + 1))
        form = ImportUploadForm(data={"target": "expenses"},
                                files={"source_file": big})
        self.assertFalse(form.is_valid())
        self.assertIn("يتجاوز الحد الأقصى",
                      str(form.errors["source_file"]))


# ================================================================ mapping
class MappingTests(BaseFixture):
    def test_suggest_mapping_arabic_and_english(self):
        mapping = svc.suggest_mapping(
            ["التاريخ", "الإدارة", "الحساب", "البيان", "المبلغ", "المورد"])
        self.assertEqual(mapping["expense_date"], "التاريخ")
        self.assertEqual(mapping["department"], "الإدارة")
        self.assertEqual(mapping["account"], "الحساب")
        self.assertEqual(mapping["description"], "البيان")
        self.assertEqual(mapping["amount"], "المبلغ")
        self.assertEqual(mapping["supplier"], "المورد")
        self.assertEqual(mapping["invoice_reference"], "")

    def test_suggest_mapping_invoice_and_date_aliases(self):
        mapping = svc.suggest_mapping(
            ["Invoice No", "Date", "amount", "Payment Method"])
        self.assertEqual(mapping["invoice_reference"], "Invoice No")
        self.assertEqual(mapping["expense_date"], "Date")
        self.assertEqual(mapping["amount"], "amount")
        self.assertEqual(mapping["payment_method"], "Payment Method")


# ================================================================ validation
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ValidationTests(BaseFixture):
    def _job(self, body: str, name="v.csv"):
        return self.extract(name, (CSV_HEAD + body).encode("utf-8"))

    def test_all_valid_summary(self):
        job = self._job(CSV_ROWS)
        summary = svc.validate_job(job, self.finance)
        job.refresh_from_db()
        self.assertEqual(job.status, "validated")
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["valid"], 2)
        self.assertEqual(summary["invalid"], 0)
        self.assertEqual(summary["duplicate"], 0)
        self.assertEqual(summary["errors"], 0)
        # ready payload carries FK ids + iso date
        row = job.rows[0]
        self.assertEqual(row["ready"]["expense_date"], "2026-01-15")
        self.assertEqual(row["ready"]["department_id"], self.dept.pk)
        self.assertEqual(row["ready"]["amount"], "150.50")
        self.assertEqual([e["event"] for e in job.job_log][-1],
                         "validation_completed")

    def test_invalid_rows_matrix(self):
        body = (
            "2026-01-15,OPS,5102,SUP-01,No amount,,INV-B1,USD,transfer\n"
            "not-a-date,OPS,5102,SUP-01,Bad date,10,INV-B2,USD,transfer\n"
            "2026-01-15,NOPE,5102,SUP-01,Bad dept,10,INV-B3,USD,transfer\n"
            "2026-01-15,OPS,5102,SUP-9,Dead supplier,10,INV-B4,USD,transfer\n"
            "2026-01-15,OPS,1100,SUP-01,Asset account,10,INV-B5,USD,transfer\n"
            "2026-01-15,OPS,5102,SUP-01,,10,INV-B6,USD,transfer\n"
            "2026-01-15,OPS,5102,SUP-01,Negative,-5,INV-B7,USD,transfer\n"
        )
        job = self._job(body)
        summary = svc.validate_job(job, self.finance)
        self.assertEqual(summary["total"], 7)
        self.assertEqual(summary["valid"], 0)
        self.assertEqual(summary["invalid"], 7)
        messages = " ".join(e["message"] for e in summary["error_list"])
        self.assertIn("المبلغ", messages)          # missing + negative
        self.assertIn("تاريخ غير صالح", messages)  # bad date
        self.assertIn("الإدارة", messages)         # unknown dept
        self.assertIn("غير نشط", messages)         # inactive supplier
        self.assertIn("مصروفات", messages)         # asset account

    def test_closed_period_error_for_finance_warning_for_admin(self):
        body = "2026-03-05,OPS,5102,SUP-01,March posting,10,INV-C1,USD,transfer\n"
        job = self._job(body)
        summary = svc.validate_job(job, self.finance)
        self.assertEqual(summary["valid"], 0)
        self.assertIn("periods.post_closed",
                      summary["error_list"][0]["message"])
        # re-validate same job as admin (holds periods.post_closed)
        job2 = self._job(body, name="v2.csv")
        summary2 = svc.validate_job(job2, self.admin)
        self.assertEqual(summary2["valid"], 1)
        self.assertGreaterEqual(summary2["warnings"], 1)

    def test_in_file_duplicate_flagged(self):
        row = ("2026-01-15,OPS,5102,SUP-01,Office supplies,150.50,INV-A1,"
               "USD,transfer\n")
        job = self._job(row + row)
        summary = svc.validate_job(job, self.finance)
        self.assertEqual(summary["duplicate"], 1)
        self.assertEqual(summary["valid"], 1)
        self.assertIn("مكرر داخل الملف",
                      " ".join(e["message"] for e in summary["error_list"]))

    def test_db_duplicate_flagged(self):
        Expense.objects.create(
            expense_number="EXP-2026-00099", expense_date=date(2026, 1, 5),
            period=self.p_jan, department=self.dept, account=self.acc,
            supplier=self.sup1, description="existing",
            amount=D("99"), invoice_reference="INV-EXIST",
            created_by=self.finance)
        row = ("2026-01-05,OPS,5102,SUP-01,Same invoice,99,INV-EXIST,"
               "USD,transfer\n")
        job = self._job(row)
        summary = svc.validate_job(job, self.finance)
        self.assertEqual(summary["duplicate"], 1)
        self.assertIn("قاعدة البيانات",
                      " ".join(e["message"] for e in summary["error_list"]))

    def test_unmapped_required_field_rejected(self):
        job = self._job(
            "2026-01-15,OPS,5102,SUP-01,X,1,INV-M1,USD,transfer\n")
        job.column_map = {"expense_date": "Date"}  # required fields missing
        job.save()
        with self.assertRaises(ValidationError) as ctx:
            svc.validate_job(job, self.finance)
        self.assertIn("مطابقة الأعمدة غير مكتملة", ctx.exception.messages[0])

    def test_summary_arithmetic_invariant(self):
        body = (
            CSV_ROWS +
            "2026-01-15,OPS,5102,SUP-01,Office supplies,150.50,INV-A1,"
            "USD,transfer\n"
            "bad,OPS,5102,SUP-01,X,1,INV-D,USD,transfer\n")
        job = self._job(body)
        s = svc.validate_job(job, self.finance)
        self.assertEqual(s["total"], s["valid"] + s["invalid"] + s["duplicate"])


# ================================================================ run/import
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class RunImportTests(BaseFixture):
    def _validated_job(self, body=CSV_ROWS):
        job = self.extract("r.csv", (CSV_HEAD + body).encode("utf-8"))
        svc.validate_job(job, self.finance)
        job.refresh_from_db()
        return job

    def test_confirm_creates_expenses_atomically(self):
        job = self._validated_job()
        imported = svc.run_import(job, self.finance)
        job.refresh_from_db()
        self.assertEqual(imported, 2)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.imported_count, 2)
        self.assertEqual(Expense.objects.count(), 2)
        e = Expense.objects.get(expense_date=date(2026, 1, 15))
        self.assertEqual(e.amount, D("150.50"))
        self.assertEqual(e.department_id, self.dept.pk)
        self.assertEqual(e.expense_category_id, self.cat.pk)  # inherited
        self.assertEqual(e.invoice_reference, "INV-A1")
        self.assertTrue(e.expense_number.startswith("EXP-2026-"))
        events = [ev["event"] for ev in job.job_log]
        self.assertIn("import_completed", events)
        log = AuditLog.objects.get(action="data_imported")
        self.assertEqual(log.diff["imported"], 2)
        self.assertEqual(log.diff["target"], "expenses")

    def test_invalid_rows_never_imported(self):
        body = CSV_ROWS + (
            "2026-01-15,OPS,1100,SUP-01,Asset row,10,INV-E1,USD,transfer\n")
        job = self._validated_job(body)
        imported = svc.run_import(job, self.finance)
        self.assertEqual(imported, 2)
        self.assertEqual(Expense.objects.count(), 2)
        self.assertEqual(job.summary["invalid"], 1)

    def test_original_file_never_deleted(self):
        job = self._validated_job()
        svc.run_import(job, self.finance)
        job.refresh_from_db()
        self.assertTrue(job.source_file.storage.exists(job.source_file.name))

    def test_confirm_guard_states(self):
        job = self.extract("g.csv", (CSV_HEAD + CSV_ROWS).encode("utf-8"))
        with self.assertRaises(ValidationError):
            svc.run_import(job, self.finance)          # not validated yet
        svc.validate_job(job, self.finance)
        job.refresh_from_db()
        svc.run_import(job, self.finance)
        job.refresh_from_db()
        with self.assertRaises(ValidationError):
            svc.run_import(job, self.finance)          # already completed

    def test_approval_reference_stamps_approver(self):
        body = ("2026-01-10,OPS,5102,SUP-01,Needs approval,300,INV-F1,"
                "USD,transfer\n")
        # approval column not in default header — extend header manually
        head = CSV_HEAD.rstrip("\n") + ",Approval\n"
        job = self.extract("appr.csv", (head + body.rstrip("\n") + ",DEC-99\n")
                           .encode("utf-8"))
        self.assertEqual(job.column_map.get("approval_reference"), "Approval")
        svc.validate_job(job, self.finance)
        job.refresh_from_db()
        svc.run_import(job, self.finance)
        e = Expense.objects.get()
        self.assertEqual(e.approval_reference, "DEC-99")
        self.assertEqual(e.approved_by_id, self.finance.pk)
        self.assertIsNotNone(e.approved_at)

    def test_cancel_keeps_file(self):
        job = self.extract("c.csv", CSV_HEAD.encode("utf-8"))
        svc.cancel_job(job, self.admin)
        job.refresh_from_db()
        self.assertEqual(job.status, "cancelled")
        self.assertTrue(job.source_file.storage.exists(job.source_file.name))


# ================================================================ HTTP
@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ImportHttpTests(BaseFixture):
    def _c(self, user):
        c = Client()
        c.force_login(user)
        return c

    def _post_upload(self, c, name="up.csv", content=None):
        content = content or (CSV_HEAD + CSV_ROWS).encode("utf-8")
        return c.post(reverse("imports:new"), {
            "target": "expenses",
            "source_file": SimpleUploadedFile(name, content)})

    def _mapping_post(self, job):
        data = {f"map-{k}": v for k, v in (job.column_map or {}).items()}
        return data

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("imports:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_roles_rbac(self):
        self.assertEqual(
            self._c(self.auditor).get(reverse("imports:list")).status_code,
            403)
        self.assertEqual(
            self._c(self.mgmt).get(reverse("imports:new")).status_code, 403)
        self.assertEqual(
            self._c(self.finance).get(reverse("imports:list")).status_code, 200)
        self.assertEqual(
            self._c(self.finance).get(reverse("imports:new")).status_code, 200)

    def test_full_http_flow_upload_validate_confirm(self):
        c = self._c(self.finance)
        response = self._post_upload(c)
        self.assertEqual(response.status_code, 302)
        job = ImportJob.objects.get()
        self.assertEqual(job.status, "extracted")
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="import_job",
            entity_id=str(job.pk)).exists())
        # detail renders preview + mapping
        detail = c.get(reverse("imports:detail", args=[job.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "مطابقة الأعمدة")
        self.assertContains(detail, "Office supplies")
        # validate
        response = c.post(reverse("imports:validate", args=[job.pk]),
                          self._mapping_post(job))
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, "validated")
        detail = c.get(reverse("imports:detail", args=[job.pk]))
        self.assertContains(detail, "إجمالي الصفوف")
        self.assertContains(detail, "صفوف صالحة")
        # confirm
        response = c.post(reverse("imports:confirm", args=[job.pk]))
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(Expense.objects.count(), 2)
        self.assertTrue(AuditLog.objects.filter(
            action="data_imported", entity_id=str(job.pk)).exists())
        # original file downloadable + audited
        response = c.get(reverse("imports:file", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content)
        self.assertIn(b"Office supplies", body)
        self.assertTrue(AuditLog.objects.filter(
            action="import_file_downloaded", entity_id=str(job.pk)).exists())

    def test_auditor_cannot_run_pipeline(self):
        job = self.extract("x.csv", (CSV_HEAD + CSV_ROWS).encode("utf-8"))
        ca = self._c(self.auditor)
        self.assertEqual(
            ca.post(reverse("imports:confirm", args=[job.pk])).status_code,
            403)
        self.assertEqual(Expense.objects.count(), 0)

    def test_validate_missing_mapping_shows_arabic_error(self):
        c = self._c(self.finance)
        self._post_upload(c, name="m.csv", content=CSV_HEAD.encode("utf-8"))
        job = ImportJob.objects.get()
        response = c.post(reverse("imports:validate", args=[job.pk]),
                          {"map-expense_date": "Date"}, follow=True)
        self.assertContains(response, "إلزامية")

    def test_cancel_http(self):
        c = self._c(self.finance)
        self._post_upload(c, name="z.csv", content=CSV_HEAD.encode("utf-8"))
        job = ImportJob.objects.get()
        response = c.post(reverse("imports:cancel", args=[job.pk]))
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, "cancelled")
        self.assertTrue(job.source_file.storage.exists(job.source_file.name))

    def test_list_shows_jobs(self):
        self.extract("shown.csv", CSV_HEAD.encode("utf-8"))
        response = self._c(self.finance).get(reverse("imports:list"))
        self.assertContains(response, "shown.csv")


# ================================================================ catalog
class CatalogInvariantTests(TestCase):
    def test_catalog_stays_30_and_import_codes_exist(self):
        self.assertEqual(len(PERMISSIONS), 30)
        self.assertIn("imports.view", ALL_CODES)
        self.assertIn("imports.run", ALL_CODES)
        expect = {
            "imports:list": "imports.view",
            "imports:detail": "imports.view",
            "imports:file": "imports.view",
            "imports:new": "imports.run",
            "imports:validate": "imports.run",
            "imports:confirm": "imports.run",
            "imports:cancel": "imports.run",
        }
        for name, code in expect.items():
            self.assertEqual(URL_PERMISSIONS[name], code)
