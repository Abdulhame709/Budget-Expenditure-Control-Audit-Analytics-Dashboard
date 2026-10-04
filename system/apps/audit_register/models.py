"""PHASE 9 — Audit Test Engine models.

DB-managed rules: the 14 approved tests (reused from the previous project's
catalog as REFERENCE) live as rows in `audit_tests` — add/edit/enable/disable
from the UI under existing permission codes. Every threshold carries a
Synthetic/Training Rule declaration; none is a real client policy.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditTest(models.Model):
    """One audit test definition — metadata + DB-managed parameters."""

    DOMAIN_CHOICES = [
        ("budget", "الموازنة"),
        ("procurement", "المشتريات"),
        ("expense", "المصروفات"),
        ("general", "عام"),
    ]
    RISK_CHOICES = [("Low", "منخفض"), ("Medium", "متوسط"), ("High", "مرتفع")]

    test_code = models.CharField(
        "Test ID", max_length=20, unique=True,
        help_text="مثال: T-EXP-03 — معرّف فريد للاختبار.")
    name = models.CharField("Name", max_length=200)
    domain = models.CharField(
        "النطاق", max_length=20, choices=DOMAIN_CHOICES, default="general")
    objective = models.TextField("Objective — الهدف")
    rule_text = models.TextField(
        "Rule — القاعدة")
    parameters = models.JSONField(
        "Parameters — المعاملات (DB-managed)", default=dict, blank=True)
    data_source = models.CharField("Data Source", max_length=255)
    expected_result = models.TextField("Expected Result")
    exception_type = models.CharField(
        "Exception Type", max_length=200,
        help_text="نوع الاستثناء الافتراضي (قد يصدر المنفّذ أنواعًا فرعية).")
    default_risk = models.CharField(
        "Default Risk", max_length=6, choices=RISK_CHOICES, default="Medium")
    auditor_action = models.TextField("Auditor Action — إجراء المدقّق")
    is_active = models.BooleanField("Active/Inactive — مفعّل", default=True)
    engine_key = models.CharField(
        "محرّك التنفيذ", max_length=60,
        help_text="مفتاح المنفّذ المسجّل في الـ engine — يسمح بإنشاء اختبارات "
                  "متعددة بنفس المنطق بمعاملات مختلفة.")
    synthetic_rule = models.BooleanField(
        "قاعدة تدريبية (Synthetic/Training Rule)", default=True,
        help_text="افتراض تدريبي — ليست سياسة معتمدة من جهة حقيقية.")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_audit_tests",
        verbose_name="أنشئ بواسطة")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="updated_audit_tests",
        verbose_name="عدّل بواسطة")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "audit_tests"
        verbose_name = "اختبار رقابي"
        verbose_name_plural = "الاختبارات الرقابية"
        ordering = ["test_code"]

    def __str__(self):
        return f"{self.test_code} — {self.name}"

    @property
    def declaration(self) -> str:
        if not self.synthetic_rule:
            return ""
        return ("قاعدة تدريبية اصطناعية (Synthetic/Training Rule) — "
                "عتبة/منطق افتراضي للاختبار التدريبي، ليست سياسة معتمدة.")


class AuditRun(models.Model):
    """One execution of one or more tests — stored with totals."""

    MODE_SINGLE = "single"
    MODE_SELECTED = "selected"
    MODE_ALL = "all_active"
    MODE_CHOICES = [
        (MODE_SINGLE, "اختبار واحد"),
        (MODE_SELECTED, "اختبارات محددة"),
        (MODE_ALL, "كل الاختبارات المفعّلة"),
    ]
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "قيد التنفيذ"),
        (STATUS_COMPLETED, "مكتمل"),
        (STATUS_FAILED, "فشل"),
    ]

    run_number = models.CharField(
        "رقم التشغيل", max_length=20, unique=True, db_index=True)
    mode = models.CharField(
        "النمط", max_length=12, choices=MODE_CHOICES, default=MODE_ALL)
    status = models.CharField(
        "الحالة", max_length=12, choices=STATUS_CHOICES,
        default=STATUS_RUNNING, db_index=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_runs",
        verbose_name="نفّذه")
    tests_total = models.PositiveSmallIntegerField(default=0)
    tests_pass = models.PositiveSmallIntegerField("ناجح (pass)", default=0)
    tests_flagged = models.PositiveSmallIntegerField(
        "مُعلَّم (flagged)", default=0)
    tests_fail = models.PositiveSmallIntegerField("فشل (fail)", default=0)
    exceptions_total = models.PositiveIntegerField(
        "إجمالي الاستثناءات", default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "audit_runs"
        verbose_name = "تشغيل اختبارات"
        verbose_name_plural = "تشغيلات الاختبارات"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.run_number} ({self.get_mode_display()})"

    @property
    def summary_line(self) -> str:
        return (f"pass {self.tests_pass} · flagged {self.tests_flagged} · "
                f"fail {self.tests_fail} · استثناءات {self.exceptions_total}")


class AuditTestResult(models.Model):
    """Per-run, per-test outcome: pass / flagged / fail + explanation."""

    STATUS_PASS = "pass"
    STATUS_FLAGGED = "flagged"
    STATUS_FAIL = "fail"
    STATUS_CHOICES = [
        (STATUS_PASS, "ناجح (pass)"),
        (STATUS_FLAGGED, "مُعلَّم (flagged)"),
        (STATUS_FAIL, "فشل (fail)"),
    ]

    run = models.ForeignKey(
        AuditRun, on_delete=models.CASCADE, related_name="results")
    test = models.ForeignKey(
        AuditTest, on_delete=models.PROTECT, related_name="results")
    status = models.CharField(
        "النتيجة", max_length=10, choices=STATUS_CHOICES, db_index=True)
    records_checked = models.PositiveIntegerField("سجلات مفحوصة", default=0)
    exceptions_count = models.PositiveIntegerField("عدد الاستثناءات", default=0)
    explanation = models.TextField(
        "لماذا هذه النتيجة — تفسير للمدقّق", blank=True)
    params_snapshot = models.JSONField(
        "لقطة المعاملات وقت التشغيل (تتبّع)", default=dict, blank=True)
    error = models.TextField("خطأ التنفيذ", blank=True)
    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_test_results"
        verbose_name = "نتيجة اختبار"
        verbose_name_plural = "نتائج الاختبارات"
        ordering = ["test__test_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "test"], name="uq_run_test_result"),
        ]

    def __str__(self):
        return f"{self.run.run_number} / {self.test.test_code}: {self.status}"


class AuditException(models.Model):
    """A flagged record — traceable to its source transaction."""

    SEVERITY_CHOICES = [
        ("S1", "S1 — مؤشر ملين"),
        ("S2", "S2 — رقابي مؤكد"),
        ("S3", "S3 — مباشر"),
    ]
    RISK_CHOICES = [("High", "مرتفع"), ("Medium", "متوسط"), ("Low", "منخفض")]
    STATUS_OPEN = "open"
    STATUS_ACK = "acknowledged"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_OPEN, "مفتوح"),
        (STATUS_ACK, "قيد الدراسة"),
        (STATUS_RESOLVED, "مُعالج"),
    ]

    run = models.ForeignKey(
        AuditRun, on_delete=models.CASCADE, related_name="exceptions")
    result = models.ForeignKey(
        AuditTestResult, on_delete=models.CASCADE, related_name="exceptions")
    test = models.ForeignKey(
        AuditTest, on_delete=models.PROTECT, related_name="exceptions")
    test_code = models.CharField("لقطة Test ID", max_length=20)

    source_type = models.CharField(
        "نوع المصدر", max_length=40,
        help_text="expense / procurement / budget_combination …")
    source_id = models.CharField("معرّف المصدر", max_length=64)
    source_ref = models.JSONField(
        "مرجع إضافي للتتبّع (إدارات/حسابات/فترات)", default=dict, blank=True)

    exception_type = models.CharField("Exception Type", max_length=100)
    title = models.CharField("عنوان مختصر", max_length=255)
    explanation = models.TextField(
        "لماذا سُجِّل — قيم فعلية مقابل عتبات الاختبار")
    amount = models.DecimalField(
        "المبلغ", max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField("العملة", max_length=3, blank=True)
    control_severity = models.CharField(
        "شدة الخلل", max_length=2, choices=SEVERITY_CHOICES, default="S2")
    risk_level = models.CharField(
        "مستوى الخطر", max_length=6, choices=RISK_CHOICES, default="Medium")
    risk_rule_ref = models.CharField(
        "مرجع قاعدة الخطر", max_length=6, blank=True)

    status = models.CharField(
        "الحالة", max_length=12, choices=STATUS_CHOICES,
        default=STATUS_OPEN, db_index=True)
    status_note = models.TextField("ملاحظة المعالجة", blank=True)
    auditor_action = models.TextField(
        "Auditor Action — إجراء المدقّق (لقطة من الاختبار وقت الاكتشاف)",
        blank=True)
    evidence = models.FileField(
        "Evidence — دليل مرفق", upload_to="evidence/%Y/%m/", blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="handled_audit_exceptions",
        verbose_name="عالجه")
    handled_at = models.DateTimeField(null=True, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_exceptions"
        verbose_name = "استثناء رقابي"
        verbose_name_plural = "سجل الاستثناءات"
        ordering = [
            "status", "-risk_level", "-amount", "test_code", "source_id"]
        indexes = [
            models.Index(fields=["run", "status"], name="ix_aexc_run_status"),
            models.Index(fields=["risk_level"], name="ix_aexc_risk"),
        ]

    def __str__(self):
        return f"[{self.test_code}] {self.title} ({self.risk_level})"

    @property
    def findings(self):
        """Findings linked to this exception (chain: Exception → Finding)."""
        return AuditFinding.objects.filter(exceptions=self)


class AuditFinding(models.Model):
    """PHASE 10 — a Finding raised from exceptions, with recommendation
    and management action. Cause is only allowed when evidence-supported.
    """

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "مفتوح"),
        (STATUS_IN_PROGRESS, "قيد المعالجة"),
        (STATUS_CLOSED, "مُغلق"),
    ]
    RISK_CHOICES = [("High", "مرتفع"), ("Medium", "متوسط"), ("Low", "منخفض")]

    finding_code = models.CharField(
        "رقم النتيجة", max_length=20, unique=True, db_index=True)
    title = models.CharField("Finding — النتيجة", max_length=255)
    criteria = models.TextField(
        "Criteria — المعيار",
        help_text="السياسة/المعيار الذي خُالف (مرجع القاعدة).")
    condition = models.TextField(
        "Condition — الوضع الفعلي",
        help_text="الحالة الواقعية المثبتة بالأدلة.")
    impact = models.TextField(
        "Impact — الأثر",
        help_text="الأثر الرقابي/المالي المقدر — وصف نوعي بلا نسب مخترعة.")
    cause = models.TextField(
        "Cause — السبب", blank=True,
        help_text="يُملأ ONLY عند توفر دليل مباشر يدعمه — وإلا يُترك فارغًا.")
    cause_supported = models.BooleanField(
        "السبب مدعوم بدليل", default=False)
    risk_level = models.CharField(
        "Risk Level", max_length=6, choices=RISK_CHOICES, default="Medium")
    recommendation = models.TextField(
        "Recommendation — التوصية")
    management_action = models.TextField(
        "Management Action — إجراء الإدارة", blank=True)
    status = models.CharField(
        "Status", max_length=15, choices=STATUS_CHOICES,
        default=STATUS_OPEN, db_index=True)
    status_note = models.TextField("ملاحظة الحالة", blank=True)

    exceptions = models.ManyToManyField(
        AuditException, related_name="linked_findings",
        verbose_name="الاستثناءات المرتبطة")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_findings",
        verbose_name="أنشئ بواسطة")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="updated_findings",
        verbose_name="عدّل بواسطة")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "audit_findings"
        verbose_name = "نتيجة رقابية (Finding)"
        verbose_name_plural = "النتائج والتوصيات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.finding_code} — {self.title}"

    @property
    def risk_choices_display(self):
        return dict(self.RISK_CHOICES).get(self.risk_level, self.risk_level)
