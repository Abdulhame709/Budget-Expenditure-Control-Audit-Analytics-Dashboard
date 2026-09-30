"""PHASE 8 — Import Pipeline models.

One table: `import_jobs` — every upload is a logged job that walks
Upload → Extract → Preview/Mapping → Validation → Confirmation → Import → Log.
The original file is NEVER deleted (kept as evidence).
"""
from __future__ import annotations

import json

from django.conf import settings
from django.db import models
from django.utils import timezone


class ImportJob(models.Model):
    """A single import run — file + extraction + mapping + validation + log."""

    TARGET_EXPENSES = "expenses"
    TARGET_CHOICES = [
        (TARGET_EXPENSES, "المصروفات الفعلية"),
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
