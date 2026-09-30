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
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.reference.models import Department, ExpenseCategory, FiscalYear, Account

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
