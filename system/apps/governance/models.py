"""governance: append-only Audit Trail (approved Phase-1 schema: audit_logs)."""
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """سجل عمليات حساسة — يُضاف فقط (لا تعديل ولا حذف من التطبيق)."""

    ACTION_CHOICES = [
        ("login", "تسجيل دخول"),
        ("login_failed", "محاولة دخول فاشلة"),
        ("logout", "تسجيل خروج"),
        ("user_created", "إنشاء مستخدم"),
        ("user_updated", "تعديل مستخدم"),
        ("roles_changed", "تغيير أدوار"),
        ("password_changed", "تغيير كلمة مرور"),
        ("user_status_changed", "تفعيل/تعطيل مستخدم"),
        # PHASE 4 — reference data lifecycle
        ("entity_created", "إنشاء سجل مرجعي"),
        ("entity_updated", "تعديل سجل مرجعي"),
        ("entity_deleted", "حذف سجل مرجعي"),
        ("period_status_changed", "فتح/إغلاق فترة شهرية"),
        ("closed_period_override", "تسجيل في فترة مغلقة"),
        # PHASE 5 — budget lifecycle
        ("budget_approved", "اعتماد نسخة ميزانية"),
        ("budget_unapproved", "إلغاء اعتماد نسخة ميزانية"),
        ("budget_version_created", "إنشاء نسخة ميزانية (مراجعة)"),
        # PHASE 6 — expenses
        ("expenses_exported", "تصدير المصروفات (CSV)"),
        ("expense_attachment_viewed", "عرض مستند مصروف مرفق"),
        # PHASE 7 — procurement
        ("procurement_attachment_viewed", "عرض مستند مشتريات مرفق"),
        # PHASE 8 — import pipeline
        ("data_imported", "تنفيذ عملية استيراد"),
        ("import_file_downloaded", "تنزيل ملف استيراد أصلي"),
        # PHASE 10 — audit cycle
        ("exception_evidence_viewed", "عرض دليل استثناء رقابي"),
        # PHASE 12 — attachments + report exports
        ("attachment_uploaded", "رفع مرفق"),
        ("attachment_viewed", "عرض مرفق"),
        ("attachment_downloaded", "تنزيل مرفق"),
        ("report_exported", "تصدير تقرير"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_events", verbose_name="المنفّذ",
    )
    actor_label = models.CharField(
        "اسم المنفّذ (لقطة)", max_length=150, blank=True, db_index=True,
        help_text="لقطة اسم المستخدم تبقى حتى لو حُذف الحساب.",
    )
    action = models.SlugField("العملية", max_length=50, choices=ACTION_CHOICES, db_index=True)
    entity_type = models.SlugField("نوع الكيان", max_length=50, db_index=True)
    entity_id = models.CharField("معرّف الكيان", max_length=60, blank=True, db_index=True)
    diff = models.JSONField(
        "التغيير (قبل/بعد)", default=dict, blank=True,
        help_text="الحقول المعدّلة مع قيمها السابقة والجديدة — بلا كلمات مرور أبدًا.",
    )
    context = models.JSONField("سياق", default=dict, blank=True)
    created_at = models.DateTimeField("الوقت", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        verbose_name = "سجل تدقيق"
        verbose_name_plural = "سجل التدقيق"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id", "created_at"],
                         name="ix_audit_entity_time"),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}#{self.entity_id}"


class Attachment(models.Model):
    """PHASE 12 — مرفق عام مرتبط بكيان (مصروف/مشتريات/استثناء/نتيجة).

    ربط عام (entity_type + entity_id) لتجنّب استيراد نماذج التطبيقات
    الأخرى داخل governance. البيانات الوصفية (metadata) تُحسب وقت الرفع.
    """

    ENTITY_CHOICES = [
        ("expense", "مصروف"),
        ("procurement", "مشتريات"),
        ("audit_exception", "استثناء رقابي"),
        ("audit_finding", "نتيجة رقابية"),
    ]

    file = models.FileField("الملف", upload_to="attachments/%Y/%m/")
    title = models.CharField("العنوان", max_length=200, blank=True)
    entity_type = models.SlugField(
        "نوع الكيان", max_length=30, choices=ENTITY_CHOICES)
    entity_id = models.CharField("معرّف الكيان", max_length=60, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="attachments_uploaded",
        verbose_name="رُفع بواسطة")
    uploaded_at = models.DateTimeField("وقت الرفع", auto_now_add=True,
                                       db_index=True)
    size = models.PositiveBigIntegerField("الحجم (بايت)", default=0)
    content_type = models.CharField("نوع الملف", max_length=100, blank=True)

    class Meta:
        db_table = "attachments"
        verbose_name = "مرفق"
        verbose_name_plural = "المرفقات"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_entity_type_display()}#{self.entity_id}: {self.file.name}"

    @property
    def size_display(self) -> str:
        kb = self.size / 1024
        return f"{kb:,.1f} KB" if kb < 1024 else f"{kb / 1024:,.2f} MB"

    def get_entity_label(self) -> str:
        label = dict(self.ENTITY_CHOICES).get(self.entity_type, "كيان")
        return f"{label} #{self.entity_id}"

    def get_entity_link(self) -> str:
        from django.urls import reverse
        route = {
            "expense": "expenses:detail",
            "procurement": "procurement:detail",
            "audit_exception": "audit:exception_detail",
            "audit_finding": "audit:finding_detail",
        }.get(self.entity_type, "home")
        try:
            return reverse(route, args=[self.entity_id])
        except Exception:
            return reverse("home")


class CloudSyncRun(models.Model):
    """سجل تنفيذ مزامنة آمنة من قاعدة السحابة إلى القاعدة المحلية."""

    STATUS_CHOICES = [
        ("running", "قيد التنفيذ"),
        ("completed", "مكتملة"),
        ("partial", "مكتملة مع تعارضات"),
        ("failed", "فشلت"),
    ]

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="running")
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cloud_sync_runs",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        db_table = "cloud_sync_runs"
        ordering = ["-started_at"]


class CloudSyncRecordState(models.Model):
    """بصمة آخر نسخة سحابية ناجحة، لاكتشاف التعارض دون مسح المحلي."""

    model_label = models.CharField(max_length=120)
    object_pk = models.CharField(max_length=128)
    cloud_hash = models.CharField(max_length=64)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cloud_sync_record_states"
        constraints = [
            models.UniqueConstraint(
                fields=["model_label", "object_pk"],
                name="uq_cloud_sync_record_state",
            ),
        ]
