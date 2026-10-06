"""PHASE 5 — Budget Management (الموازنة).

Structure (audit-oriented, all amounts NUMERIC(14,2) per C11):

    Budget (one per fiscal year — unique)
      └── BudgetVersion (draft → approved; revision = new version;
                          THE analysis version = latest approved)
            └── BudgetLine (department × account [× category]
                            + 12 monthly amounts; annual = their sum)

All figures live in PostgreSQL — the UI never holds fixed numbers.
Foundation for Budget-vs-Actual / Variance / Out-of-Budget is provided
by apps.budget.services (no audit engine in this phase).
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.reference.models import (
    Account,
    Currency,
    Department,
    Employee,
    ExpenseCategory,
    FiscalYear,
)

MONTH_FIELDS = [f"m{m:02d}" for m in range(1, 13)]
MAX_AMOUNT = 999_999_999_999.99  # NUMERIC(14,2)


def _amount_field(label: str) -> models.DecimalField:
    return models.DecimalField(
        label, max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التعديل", auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(class)s_created", verbose_name="أُنشئ بواسطة",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="%(class)s_updated", verbose_name="عُدّل بواسطة",
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------- header
class Budget(TimeStampedModel):
    """Fiscal budget header — exactly one budget per fiscal year."""

    fiscal_year = models.OneToOneField(
        FiscalYear, on_delete=models.PROTECT, related_name="budget",
        verbose_name="السنة المالية",
    )
    name = models.CharField("اسم الميزانية", max_length=150)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        db_table = "budgets"
        verbose_name = "ميزانية"
        verbose_name_plural = "الموازنة"
        ordering = ["-fiscal_year__year"]

    def __str__(self):
        return f"{self.name} ({self.fiscal_year.code})"

    @property
    def latest_version(self):
        return self.versions.order_by("-version").first()

    @property
    def analysis_version(self):
        """THE version used in analysis — latest APPROVED (None if none)."""
        return self.versions.filter(status=BudgetVersion.STATUS_APPROVED).order_by(
            "-version"
        ).first()

    def clean(self):
        super().clean()
        if self.fiscal_year_id:
            clash = Budget.objects.filter(
                fiscal_year=self.fiscal_year_id
            ).exclude(pk=self.pk)
            if clash.exists():
                raise ValidationError(
                    {"fiscal_year":
                        f"توجد ميزانية مسبقة لهذه السنة المالية ({clash.first()})."}
                )


# ---------------------------------------------------------------- version
class BudgetVersion(TimeStampedModel):
    """A numbered revision of a budget. Status: draft ⇄ approved.
    Approved versions are LOCKED (edits require a new revision)."""

    STATUS_DRAFT = "draft"
    STATUS_APPROVED = "approved"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "مسودة"),
        (STATUS_APPROVED, "معتمدة"),
    ]

    budget = models.ForeignKey(
        Budget, on_delete=models.CASCADE, related_name="versions",
        verbose_name="الميزانية",
    )
    version = models.PositiveSmallIntegerField("رقم النسخة", default=1)
    status = models.CharField(
        "الحالة", max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="budget_approvals", verbose_name="معتمد بواسطة",
    )
    approved_at = models.DateTimeField("تاريخ الاعتماد", null=True, blank=True)
    notes = models.TextField("ملاحظات النسخة", blank=True)

    class Meta:
        db_table = "budget_versions"
        verbose_name = "نسخة ميزانية"
        verbose_name_plural = "نسخ الموازنة"
        ordering = ["budget", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "version"], name="uq_budget_version",
            ),
        ]

    def __str__(self):
        return f"{self.budget.name} — v{self.version}"

    @property
    def is_approved(self) -> bool:
        return self.status == self.STATUS_APPROVED

    @property
    def is_analysis_version(self) -> bool:
        """True only for the single version analysis uses."""
        latest = self.budget.analysis_version
        return latest is not None and latest.pk == self.pk


# ---------------------------------------------------------------- line
class BudgetLine(TimeStampedModel):
    """Manual budget entry: department × account (+category) × 12 months.

    annual_amount is DERIVED (sum of the 12 months) — enforced both in
    clean() and by a DB CHECK so totals always come from real data.
    """

    version = models.ForeignKey(
        BudgetVersion, on_delete=models.CASCADE, related_name="lines",
        verbose_name="نسخة الميزانية",
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="budget_lines",
        verbose_name="الإدارة",
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="budget_lines",
        verbose_name="الحساب",
    )
    expense_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True,
        related_name="budget_lines", verbose_name="تصنيف المصروف",
        help_text="يُورَد تلقائيًا من الحساب إن تُرك فارغًا.",
    )
    m01 = _amount_field("شهر 1")
    m02 = _amount_field("شهر 2")
    m03 = _amount_field("شهر 3")
    m04 = _amount_field("شهر 4")
    m05 = _amount_field("شهر 5")
    m06 = _amount_field("شهر 6")
    m07 = _amount_field("شهر 7")
    m08 = _amount_field("شهر 8")
    m09 = _amount_field("شهر 9")
    m10 = _amount_field("شهر 10")
    m11 = _amount_field("شهر 11")
    m12 = _amount_field("شهر 12")
    annual_amount = models.DecimalField(
        "الميزانية السنوية", max_digits=14, decimal_places=2, default=0,
        editable=False,  # derived — never typed
    )
    notes = models.TextField("ملاحظات السطر", blank=True)

    class Meta:
        db_table = "budget_lines"
        verbose_name = "سطر ميزانية"
        verbose_name_plural = "سطور الموازنة"
        ordering = ["account__code", "department__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "department", "account"],
                name="uq_budget_line",
            ),
            models.CheckConstraint(
                condition=Q(
                    annual_amount=(
                        F("m01") + F("m02") + F("m03") + F("m04")
                        + F("m05") + F("m06") + F("m07") + F("m08")
                        + F("m09") + F("m10") + F("m11") + F("m12")
                    )
                ),
                name="chk_line_annual_is_monthly_sum",
            ),
            models.CheckConstraint(
                condition=Q(annual_amount__gte=0),
                name="chk_line_annual_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.department.code}/{self.account.code} — {self.annual_amount}"

    # exposed for forms (locals() above builds the fields)
    def month_values(self) -> list:
        return [getattr(self, f) or 0 for f in MONTH_FIELDS]

    def clean(self):
        super().clean()
        errors: dict = {}
        # account must be an expense account (expenditure budget)
        if self.account_id and self.account.account_type != "expense":
            errors["account"] = (
                "سطور الميزانية تُقيَّد على حسابات نوع «مصروفات» فقط — "
                f"الحساب المحدد من نوع «{self.account.get_account_type_display()}»."
            )
        elif self.account_id and not self.account.is_operational:
            errors["account"] = "يجب اختيار حساب نشط من المستوى الخامس."
        # negative months (bypassing field validators)
        for fname in MONTH_FIELDS:
            value = getattr(self, fname, None)
            if value is not None and value < 0:
                errors[fname] = "لا تُقبل مبالغ سالبة في الميزانية."
        # category defaults from the account (clear expense classification)
        if not self.expense_category_id and self.account_id:
            self.expense_category = self.account.expense_category
        # derived annual
        if not errors:
            total = sum((getattr(self, f) or 0) for f in MONTH_FIELDS)
            self.annual_amount = total
        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------- configurable workbook templates
class BudgetPlan(TimeStampedModel):
    STATUS_DRAFT = "draft"
    STATUS_REVIEW = "review"
    STATUS_APPROVED = "approved"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "مسودة"),
        (STATUS_REVIEW, "قيد المراجعة"),
        (STATUS_APPROVED, "معتمد"),
        (STATUS_ARCHIVED, "مؤرشف"),
    ]

    name = models.CharField("اسم نموذج التخطيط", max_length=180)
    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT, related_name="budget_plans",
        verbose_name="السنة المالية",
    )
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, related_name="budget_plans",
        verbose_name="العملة",
    )
    description = models.TextField("الوصف", blank=True)
    status = models.CharField(
        "الحالة", max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT,
    )
    version = models.PositiveSmallIntegerField("رقم الإصدار", default=1)

    class Meta:
        db_table = "budget_plans"
        verbose_name = "نموذج تخطيط موازنة"
        verbose_name_plural = "نماذج تخطيط الموازنة"
        ordering = ["-fiscal_year__year", "name", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "fiscal_year", "version"],
                name="uq_budget_plan_name_year_version",
            ),
        ]

    def __str__(self):
        return f"{self.name} — {self.fiscal_year.code} (v{self.version})"

    @property
    def is_locked(self) -> bool:
        return self.status in {self.STATUS_APPROVED, self.STATUS_ARCHIVED}


class BudgetPlanSection(TimeStampedModel):
    plan = models.ForeignKey(
        BudgetPlan, on_delete=models.CASCADE, related_name="sections",
        verbose_name="نموذج التخطيط",
    )
    name = models.CharField("اسم القسم", max_length=180)
    description = models.TextField("الوصف", blank=True)
    position = models.PositiveIntegerField("الترتيب", default=1)
    default_main_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True,
        related_name="default_budget_plan_sections", verbose_name="الحساب الرئيسي الافتراضي",
    )

    class Meta:
        db_table = "budget_plan_sections"
        verbose_name = "قسم نموذج موازنة"
        verbose_name_plural = "أقسام نماذج الموازنة"
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "position"], name="uq_budget_plan_section_position",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.default_main_account_id and (
            not self.default_main_account.is_active
            or self.default_main_account.account_type != "expense"
            or self.default_main_account.level != 5
        ):
            raise ValidationError({
                "default_main_account": "يجب اختيار حساب مصروف نشط من المستوى الخامس."
            })


class BudgetPlanLine(TimeStampedModel):
    TYPE_TITLE = "title"
    TYPE_MAIN_ACCOUNT = "main_account"
    TYPE_ANALYTICAL_ACCOUNT = "analytical_account"
    TYPE_DETAIL = "detail"
    TYPE_SUBTOTAL = "subtotal"
    TYPE_TOTAL = "total"
    TYPE_NOTE = "note"
    ROW_TYPE_CHOICES = [
        (TYPE_TITLE, "عنوان"),
        (TYPE_MAIN_ACCOUNT, "حساب رئيسي"),
        (TYPE_ANALYTICAL_ACCOUNT, "حساب تحليلي"),
        (TYPE_DETAIL, "تفصيل"),
        (TYPE_SUBTOTAL, "إجمالي فرعي"),
        (TYPE_TOTAL, "إجمالي عام"),
        (TYPE_NOTE, "ملاحظة"),
    ]

    INPUT_NONE = "none"
    INPUT_ANNUAL = "annual"
    INPUT_MONTHLY = "monthly"
    INPUT_QUANTITY_PRICE = "quantity_price"
    INPUT_PERIODIC = "periodic"
    INPUT_MODE_CHOICES = [
        (INPUT_NONE, "بدون إدخال"),
        (INPUT_ANNUAL, "مبلغ سنوي"),
        (INPUT_MONTHLY, "مبالغ شهرية"),
        (INPUT_QUANTITY_PRICE, "كمية × سعر وحدة"),
        (INPUT_PERIODIC, "مبلغ دوري × عدد الفترات"),
    ]

    DIST_NONE = "none"
    DIST_EQUAL = "equal"
    DIST_MANUAL = "manual"
    DIST_SINGLE_MONTH = "single_month"
    DIST_SELECTED_MONTHS = "selected_months"
    DISTRIBUTION_CHOICES = [
        (DIST_NONE, "بدون توزيع"),
        (DIST_EQUAL, "متساوٍ على 12 شهرًا"),
        (DIST_MANUAL, "يدوي"),
        (DIST_SINGLE_MONTH, "شهر واحد"),
        (DIST_SELECTED_MONTHS, "أشهر مختارة"),
    ]

    section = models.ForeignKey(
        BudgetPlanSection, on_delete=models.CASCADE, related_name="lines",
        verbose_name="القسم",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="children", verbose_name="البند الأب",
    )
    position = models.PositiveIntegerField("الترتيب", default=1)
    row_type = models.CharField(
        "نوع الصف", max_length=24, choices=ROW_TYPE_CHOICES, default=TYPE_DETAIL,
    )
    display_name = models.CharField("اسم العرض", max_length=220)
    main_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True,
        related_name="budget_plan_main_lines", verbose_name="الحساب الرئيسي",
    )
    analytical_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True,
        related_name="budget_plan_analytical_lines", verbose_name="الحساب التحليلي",
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, blank=True,
        related_name="budget_plan_lines", verbose_name="الإدارة",
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, null=True, blank=True,
        related_name="budget_plan_lines", verbose_name="الموظف",
    )
    unit_of_measure = models.CharField("وحدة القياس", max_length=80, blank=True)
    input_mode = models.CharField(
        "طريقة الإدخال", max_length=24, choices=INPUT_MODE_CHOICES, default=INPUT_NONE,
    )
    distribution_method = models.CharField(
        "طريقة التوزيع", max_length=24, choices=DISTRIBUTION_CHOICES, default=DIST_NONE,
    )
    annual_amount = models.DecimalField(
        "المبلغ السنوي", max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
    quantity = models.DecimalField(
        "الكمية", max_digits=14, decimal_places=4, default=0,
        validators=[MinValueValidator(0)],
    )
    unit_price = models.DecimalField(
        "سعر الوحدة", max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
    periodic_amount = models.DecimalField(
        "المبلغ الدوري", max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )
    periods_count = models.PositiveSmallIntegerField("عدد الفترات", default=0)
    single_month = models.PositiveSmallIntegerField(
        "شهر الصرف", null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    selected_months = models.JSONField("الأشهر المختارة", default=list, blank=True)
    aggregate_sections = models.ManyToManyField(
        BudgetPlanSection, blank=True, related_name="aggregate_lines",
        verbose_name="الأقسام الداخلة في الإجمالي",
        help_text="يستخدم مع صفوف الإجمالي فقط، ولا يكرر المبالغ في المخرجات.",
    )
    estimation_basis = models.TextField("أساس التقدير", blank=True)
    is_included = models.BooleanField("مضمّن في الإجماليات", default=True)

    class Meta:
        db_table = "budget_plan_lines"
        verbose_name = "بند نموذج موازنة"
        verbose_name_plural = "بنود نماذج الموازنة"
        ordering = ["section__position", "position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "position"], name="uq_budget_plan_line_position",
            ),
        ]

    def __str__(self):
        return self.display_name

    @property
    def plan(self):
        return self.section.plan

    def clean(self):
        super().clean()
        errors = {}
        if self.parent_id and self.parent.section_id != self.section_id:
            errors["parent"] = "يجب أن يكون البند الأب داخل القسم نفسه."
        seen, node = set(), self.parent
        while node is not None:
            if node.pk == self.pk:
                errors["parent"] = "توجد دورة في شجرة بنود الموازنة."
                break
            if node.pk in seen:
                break
            seen.add(node.pk)
            node = node.parent
        for field_name in ("main_account", "analytical_account"):
            account = getattr(self, field_name)
            if account and (
                not account.is_active or account.account_type != "expense" or account.level != 5
            ):
                errors[field_name] = "يجب اختيار حساب مصروف نشط من المستوى الخامس."
        if self.employee and self.department and self.employee.department_id != self.department_id:
            errors["employee"] = "الموظف المختار لا يتبع الإدارة المحددة."
        if self.single_month is not None and not 1 <= self.single_month <= 12:
            errors["single_month"] = "الشهر يجب أن يكون بين 1 و12."
        invalid_months = [
            m for m in (self.selected_months or [])
            if not isinstance(m, int) or not 1 <= m <= 12
        ]
        if invalid_months:
            errors["selected_months"] = "الأشهر المختارة يجب أن تكون أرقامًا من 1 إلى 12."
        if self.distribution_method == self.DIST_SINGLE_MONTH and not self.single_month:
            errors["single_month"] = "حدد شهر الصرف."
        if self.distribution_method == self.DIST_SELECTED_MONTHS and not self.selected_months:
            errors["selected_months"] = "اختر شهرًا واحدًا على الأقل."
        if errors:
            raise ValidationError(errors)


class BudgetPlanPeriodAmount(models.Model):
    line = models.ForeignKey(
        BudgetPlanLine, on_delete=models.CASCADE, related_name="period_amounts",
        verbose_name="البند",
    )
    month = models.PositiveSmallIntegerField(
        "الشهر", validators=[MinValueValidator(1)],
    )
    amount = models.DecimalField(
        "المبلغ", max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        db_table = "budget_plan_period_amounts"
        verbose_name = "مبلغ شهري لبند الموازنة"
        verbose_name_plural = "المبالغ الشهرية لبنود الموازنة"
        ordering = ["month"]
        constraints = [
            models.UniqueConstraint(
                fields=["line", "month"], name="uq_budget_plan_line_month",
            ),
            models.CheckConstraint(
                condition=Q(month__gte=1) & Q(month__lte=12),
                name="budget_plan_month_valid",
            ),
        ]

    def __str__(self):
        return f"{self.line} — {self.month}: {self.amount}"


class BudgetTemplate(TimeStampedModel):
    """A reusable Excel-originated workbook used to design budget inputs."""

    name = models.CharField("اسم النموذج", max_length=180)
    description = models.TextField("الوصف", blank=True)
    source_filename = models.CharField("اسم الملف المصدر", max_length=255, blank=True)
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True,
        related_name="budget_templates", verbose_name="العملة",
    )
    is_active = models.BooleanField("نشط", default=True)
    workbook_metadata = models.JSONField("خصائص المصنف", default=dict, blank=True)

    class Meta:
        db_table = "budget_templates"
        verbose_name = "نموذج موازنة"
        verbose_name_plural = "نماذج الموازنة"
        ordering = ["-updated_at", "name"]

    def __str__(self):
        return self.name


class BudgetTemplateSheet(TimeStampedModel):
    PURPOSE_DETAIL = "detail"
    PURPOSE_MONTHLY = "monthly"
    PURPOSE_SUMMARY = "summary"
    PURPOSE_SUPPORTING = "supporting"
    PURPOSE_CHOICES = [
        (PURPOSE_DETAIL, "نموذج تفصيلي"),
        (PURPOSE_MONTHLY, "توزيع شهري"),
        (PURPOSE_SUMMARY, "إجماليات الحسابات الرئيسية"),
        (PURPOSE_SUPPORTING, "ورقة مساندة"),
    ]

    template = models.ForeignKey(
        BudgetTemplate, on_delete=models.CASCADE, related_name="sheets",
        verbose_name="النموذج",
    )
    name = models.CharField("اسم الورقة", max_length=180)
    position = models.PositiveSmallIntegerField("ترتيب الورقة", default=1)
    purpose = models.CharField(
        "وظيفة الورقة", max_length=20, choices=PURPOSE_CHOICES,
        default=PURPOSE_SUPPORTING,
    )
    state = models.CharField("حالة الظهور", max_length=20, default="visible")
    max_row = models.PositiveIntegerField("عدد الصفوف", default=0)
    max_column = models.PositiveIntegerField("عدد الأعمدة", default=0)
    freeze_panes = models.CharField("تثبيت الأجزاء", max_length=20, blank=True)
    merged_ranges = models.JSONField("الخلايا المدمجة", default=list, blank=True)
    layout_metadata = models.JSONField("خصائص التخطيط", default=dict, blank=True)

    class Meta:
        db_table = "budget_template_sheets"
        verbose_name = "ورقة نموذج موازنة"
        verbose_name_plural = "أوراق نماذج الموازنة"
        ordering = ["template", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "name"], name="uq_budget_template_sheet_name",
            ),
            models.UniqueConstraint(
                fields=["template", "position"], name="uq_budget_template_sheet_position",
            ),
        ]

    def __str__(self):
        return f"{self.template.name} — {self.name}"


class BudgetTemplateColumn(models.Model):
    ROLE_GENERIC = "generic"
    ROLE_ACCOUNT_CODE = "account_code"
    ROLE_ACCOUNT_NAME = "account_name"
    ROLE_ANNUAL = "annual"
    ROLE_NOTES = "notes"
    ROLE_CHOICES = [
        (ROLE_GENERIC, "عام"),
        (ROLE_ACCOUNT_CODE, "رقم الحساب"),
        (ROLE_ACCOUNT_NAME, "اسم الحساب"),
        *[(f"month_{month:02d}", f"شهر {month}") for month in range(1, 13)],
        (ROLE_ANNUAL, "الإجمالي السنوي"),
        (ROLE_NOTES, "ملاحظات"),
    ]

    sheet = models.ForeignKey(
        BudgetTemplateSheet, on_delete=models.CASCADE, related_name="columns",
        verbose_name="الورقة",
    )
    column_index = models.PositiveIntegerField("رقم العمود")
    column_letter = models.CharField("رمز العمود", max_length=5)
    title = models.CharField("عنوان العمود", max_length=255, blank=True)
    role = models.CharField(
        "وظيفة العمود", max_length=20, choices=ROLE_CHOICES,
        default=ROLE_GENERIC,
    )
    width = models.DecimalField(
        "عرض العمود", max_digits=8, decimal_places=2, null=True, blank=True,
    )
    is_hidden = models.BooleanField("مخفي", default=False)

    class Meta:
        db_table = "budget_template_columns"
        verbose_name = "عمود نموذج موازنة"
        verbose_name_plural = "أعمدة نماذج الموازنة"
        ordering = ["sheet", "column_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "column_index"], name="uq_budget_template_column",
            ),
        ]

    def __str__(self):
        return f"{self.sheet.name}!{self.column_letter}"


class BudgetTemplateRow(models.Model):
    TYPE_TITLE = "title"
    TYPE_HEADER = "header"
    TYPE_DATA = "data"
    TYPE_SUBTOTAL = "subtotal"
    TYPE_TOTAL = "total"
    TYPE_NOTE = "note"
    TYPE_CHOICES = [
        (TYPE_TITLE, "عنوان"),
        (TYPE_HEADER, "رأس جدول"),
        (TYPE_DATA, "بيانات"),
        (TYPE_SUBTOTAL, "إجمالي فرعي"),
        (TYPE_TOTAL, "إجمالي"),
        (TYPE_NOTE, "ملاحظة"),
    ]

    sheet = models.ForeignKey(
        BudgetTemplateSheet, on_delete=models.CASCADE, related_name="rows",
        verbose_name="الورقة",
    )
    row_number = models.PositiveIntegerField("رقم الصف")
    row_type = models.CharField(
        "نوع الصف", max_length=12, choices=TYPE_CHOICES, default=TYPE_DATA,
    )
    label = models.CharField("وصف الصف", max_length=500, blank=True)
    account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="budget_template_rows", verbose_name="الحساب المرتبط",
    )
    is_included = models.BooleanField("يدخل في الموازنة", default=True)
    height = models.DecimalField(
        "ارتفاع الصف", max_digits=8, decimal_places=2, null=True, blank=True,
    )
    is_hidden = models.BooleanField("مخفي", default=False)

    class Meta:
        db_table = "budget_template_rows"
        verbose_name = "صف نموذج موازنة"
        verbose_name_plural = "صفوف نماذج الموازنة"
        ordering = ["sheet", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "row_number"], name="uq_budget_template_row",
            ),
        ]

    def __str__(self):
        return f"{self.sheet.name} — صف {self.row_number}"


class BudgetTemplateCell(models.Model):
    row = models.ForeignKey(
        BudgetTemplateRow, on_delete=models.CASCADE, related_name="cells",
        verbose_name="الصف",
    )
    column = models.ForeignKey(
        BudgetTemplateColumn, on_delete=models.CASCADE, related_name="cells",
        verbose_name="العمود",
    )
    coordinate = models.CharField("مرجع الخلية", max_length=20)
    raw_value = models.TextField("القيمة", blank=True)
    formula = models.TextField("الصيغة", blank=True)
    data_type = models.CharField("نوع البيانات", max_length=12, blank=True)
    number_format = models.CharField("تنسيق الرقم", max_length=120, blank=True)
    style_metadata = models.JSONField("خصائص التنسيق", default=dict, blank=True)

    class Meta:
        db_table = "budget_template_cells"
        verbose_name = "خلية نموذج موازنة"
        verbose_name_plural = "خلايا نماذج الموازنة"
        ordering = ["row", "column__column_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["row", "column"], name="uq_budget_template_cell",
            ),
        ]

    def __str__(self):
        return f"{self.row.sheet.name}!{self.coordinate}"
