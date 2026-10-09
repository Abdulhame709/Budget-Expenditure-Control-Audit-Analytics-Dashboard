"""PHASE 8 — Import Pipeline models.

One table: `import_jobs` — every upload is a logged job that walks
Upload → Extract → Preview/Mapping → Validation → Confirmation → Import → Log.
The original file is NEVER deleted (kept as evidence).
"""
from __future__ import annotations

import json

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ImportJob(models.Model):
    """A single import run — file + extraction + mapping + validation + log."""

    TARGET_EXPENSES = "expenses"
    TARGET_FISCAL_YEARS = "fiscal_years"
    TARGET_PERIODS = "periods"
    TARGET_DEPARTMENTS = "departments"
    TARGET_EXPENSE_CATEGORIES = "expense_categories"
    TARGET_ACCOUNTS = "accounts"
    TARGET_SUPPLIERS = "suppliers"
    TARGET_BUDGET_LINES = "budget_lines"
    TARGET_PROCUREMENTS = "procurements"
    TARGET_QUOTATIONS = "quotations"
    TARGET_DETAILED_BUDGET = "detailed_budget"
    TARGET_BUDGET_MATRIX = "budget_matrix"
    TARGET_ACTUAL_MATRIX = "actual_matrix"
    TARGET_CHOICES = [
        (TARGET_FISCAL_YEARS, "السنوات المالية"),
        (TARGET_PERIODS, "الفترات الشهرية"),
        (TARGET_DEPARTMENTS, "الإدارات"),
        (TARGET_EXPENSE_CATEGORIES, "تصنيفات المصروفات"),
        (TARGET_ACCOUNTS, "الدليل المحاسبي"),
        (TARGET_SUPPLIERS, "الموردون"),
        (TARGET_BUDGET_LINES, "الموازنة التقديرية — السطور الشهرية"),
        (TARGET_BUDGET_MATRIX, "الموازنة التقديرية — حسابات مستوى 5 و6 / مستوى 5 فقط"),
        (TARGET_ACTUAL_MATRIX, "المصروفات الفعلية — إجمالي شهر واحد حسب الحساب"),
        (TARGET_DETAILED_BUDGET, "الموازنة التفصيلية الأولية (أوراق متعددة)"),
        (TARGET_EXPENSES, "المصروفات الفعلية"),
        (TARGET_PROCUREMENTS, "سجلات المشتريات"),
        (TARGET_QUOTATIONS, "عروض أسعار الموردين"),
    ]

    FORMAT_CSV = "csv"
    FORMAT_XLSX = "xlsx"
    FORMAT_PDF = "pdf"
    FORMAT_CHOICES = [
        (FORMAT_CSV, "CSV"),
        (FORMAT_XLSX, "Excel (xlsx)"),
        (FORMAT_PDF, "PDF"),
    ]

    STATUS_UPLOADED = "uploaded"
    STATUS_EXTRACTED = "extracted"
    STATUS_VALIDATED = "validated"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_UPLOADED, "مرفوع"),
        (STATUS_EXTRACTED, "مُستخرج — بانتظار المطابقة"),
        (STATUS_VALIDATED, "مُتحقق — بانتظار التأكيد"),
        (STATUS_COMPLETED, "مكتمل"),
        (STATUS_FAILED, "فشل"),
        (STATUS_CANCELLED, "ملغى"),
    ]

    target = models.CharField(
        "الهدف", max_length=30, choices=TARGET_CHOICES,
        default=TARGET_EXPENSES)
    source_file = models.FileField(
        "الملف الأصلي (يُحفظ دائمًا)", upload_to="imports/%Y/%m/")
    original_filename = models.CharField("اسم الملف الأصلي", max_length=255)
    source_sha256 = models.CharField(
        "بصمة الملف SHA-256", max_length=64, blank=True, default="",
        editable=False, db_index=True)
    file_format = models.CharField(
        "الصيغة", max_length=10, choices=FORMAT_CHOICES)
    status = models.CharField(
        "الحالة", max_length=12, choices=STATUS_CHOICES,
        default=STATUS_UPLOADED, db_index=True)

    # extraction result
    headers = models.JSONField("أعمدة الملف", default=list, blank=True)
    rows = models.JSONField(
        "الصفوف (مصدر + مطابقة + تحقق)", default=list, blank=True)
    extraction_warnings = models.JSONField(
        "تحذيرات الاستخراج", default=list, blank=True)
    ocr_used = models.BooleanField("استُخدم OCR", default=False)

    # mapping + validation
    column_map = models.JSONField(
        "مطابقة الأعمدة (حقل الهدف ← عمود الملف)", default=dict, blank=True)
    summary = models.JSONField(
        "ملخص التحقق", default=dict, blank=True)

    # result + audit log of the job itself
    imported_count = models.PositiveIntegerField("عدد الصفوف المستوردة", default=0)
    job_log = models.JSONField(
        "سجل خطوات Import Job", default=list, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="import_jobs",
        verbose_name="أنشئ بواسطة")
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        db_table = "import_jobs"
        verbose_name = "عملية استيراد"
        verbose_name_plural = "عمليات الاستيراد"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"],
                         name="ix_importjob_status_time"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_sha256"], condition=~Q(source_sha256=""),
                name="uq_importjob_source_sha256"),
        ]

    def __str__(self):
        return f"#{self.pk} {self.get_target_display()} — {self.original_filename}"

    # ------------------------------------------------------------------ log
    def log(self, event: str, **extra) -> None:
        """Append a timestamped lifecycle event to the job log (in place)."""
        entry = {"at": timezone.now().isoformat(), "event": event}
        entry.update(extra)
        self.job_log = [*(self.job_log or []), entry]

    def log_json(self) -> str:
        return json.dumps(self.job_log, ensure_ascii=False, indent=2)

    @property
    def summary_counts(self) -> dict:
        s = self.summary or {}
        return {
            "total": s.get("total", 0),
            "valid": s.get("valid", 0),
            "invalid": s.get("invalid", 0),
            "duplicate": s.get("duplicate", 0),
            "errors": s.get("errors", 0),
            "warnings": s.get("warnings", 0),
        }


class DetailedBudgetSheet(models.Model):
    """Archived sheet of a multi-sheet initial budget workbook (target=detailed_budget).
    Stores the original Arabic headers and the raw row values as-is — the
    source file is never altered, and this snapshot is the audit trail."""

    job = models.ForeignKey(
        ImportJob, on_delete=models.CASCADE, related_name="detailed_sheets",
        verbose_name="عملية الاستيراد")
    name = models.CharField("اسم الورقة", max_length=150)
    display_title = models.CharField(
        "العنوان الظاهر (صف العنوان المدمج)", max_length=300, blank=True, default="")
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التعديل", auto_now=True)
    order = models.PositiveIntegerField("ترتيب الورقة", default=0)
    headers = models.JSONField("أعمدة الورقة", default=list, blank=True)
    rows = models.JSONField("صفوف الورقة", default=list, blank=True)
    sheet_total = models.DecimalField(
        "إجمالي الورقة", max_digits=18, decimal_places=2, null=True, blank=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        db_table = "imports_detailed_budget_sheets"
        verbose_name = "ورقة موازنة تفصيلية"
        verbose_name_plural = "أوراق الموازنة التفصيلية"
        ordering = ["job", "order"]

    def __str__(self):
        return f"{self.job.pk}/{self.order} — {self.name}"
