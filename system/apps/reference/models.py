"""PHASE 4 — core reference data (البيانات المرجعية الأساسية).

Six master-data modules, all Arabic-labelled, Active/Inactive aware,
with DB-level constraints (CHECK/UNIQUE) + model-level cross-field
validation, FK RESTRICT (PROTECT) for referential integrity, and
created_by/updated_by integration with accounts.User.
"""
from __future__ import annotations

import calendar
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


class TimeStampedModel(models.Model):
    """created/updated by + timestamps — shared by every PHASE 4 module."""

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


# ---------------------------------------------------------------- fiscal year
class FiscalYear(TimeStampedModel):
    """السنة المالية — must not overlap any other fiscal year."""

    code = models.SlugField("الرمز", max_length=20, unique=True)
    name = models.CharField("الاسم", max_length=120)
    year = models.PositiveSmallIntegerField(
        "السنة", validators=[MinValueValidator(2000), MaxValueValidator(2100)],
        help_text="السنة التقويمية المقابلة، مثل 2026.",
    )
    start_date = models.DateField("تاريخ البداية")
    end_date = models.DateField("تاريخ النهاية")
    is_active = models.BooleanField("نشط", default=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        db_table = "fiscal_years"
        verbose_name = "سنة مالية"
        verbose_name_plural = "السنوات المالية"
        ordering = ["-year"]
        constraints = [
            models.CheckConstraint(
                condition=Q(start_date__lte=F("end_date")),
                name="chk_fy_start_before_end",
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def clean(self):
        super().clean()
        errors: dict = {}
        if self.start_date and self.end_date and self.start_date > self.end_date:
            errors["end_date"] = "تاريخ النهاية يجب أن يكون بعد تاريخ البداية."
        if (
            self.start_date and self.end_date and self.year
            and self.start_date.year > self.year
        ):
            errors["start_date"] = "تاريخ البداية لا يوافق السنة المحددة."
        if not errors and self.start_date and self.end_date:
            clash = (
                FiscalYear.objects.filter(
                    start_date__lte=self.end_date, end_date__gte=self.start_date
                )
                .exclude(pk=self.pk)
            )
            if clash.exists():
                other = clash.first()
                errors["start_date"] = (
                    f"تتقاطع مع السنة المالية {other.code} ({other.start_date} — {other.end_date})."
                )
        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------- monthly period
def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


class MonthlyPeriod(TimeStampedModel):
    """فترة شهرية — belongs to a fiscal year; status Open/Closed.

    Posting transactions into a Closed period is blocked unless the actor
    holds `periods.post_closed` (always logged — see reference.services).
    """

    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_OPEN, "مفتوحة"),
        (STATUS_CLOSED, "مغلقة"),
    ]

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT, related_name="periods",
        verbose_name="السنة المالية",
    )
    month = models.PositiveSmallIntegerField(
        "الشهر", validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="رقم الشهر التقويمي لبداية الفترة (1–12).",
    )
    start_date = models.DateField("تاريخ البداية")
    end_date = models.DateField("تاريخ النهاية")
    status = models.CharField(
        "الحالة (مفتوحة/مغلقة)", max_length=10, choices=STATUS_CHOICES,
        default=STATUS_OPEN,
    )
    is_active = models.BooleanField("نشط", default=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        db_table = "monthly_periods"
        verbose_name = "فترة شهرية"
        verbose_name_plural = "الفترات الشهرية"
        ordering = ["fiscal_year__year", "month"]
        constraints = [
            models.UniqueConstraint(
                fields=["fiscal_year", "month"], name="uq_period_fy_month",
            ),
            models.CheckConstraint(
                condition=Q(start_date__lte=F("end_date")),
                name="chk_period_start_before_end",
            ),
        ]

    def __str__(self):
        return f"{self.fiscal_year.code} — الشهر {self.month}"

    @property
    def is_closed(self) -> bool:
        return self.status == self.STATUS_CLOSED

    def clean(self):
        super().clean()
        errors: dict = {}
        if self.month and not (1 <= self.month <= 12):
            errors["month"] = "رقم الشهر يجب أن يكون بين 1 و 12."
        fy = self.fiscal_year
        if fy and self.start_date and self.end_date:
            if self.start_date < fy.start_date or self.end_date > fy.end_date:
                errors["start_date"] = (
                    "الفترات يجب أن تقع داخل نطاق السنة المالية "
                    f"({fy.start_date} — {fy.end_date})."
                )
        if self.month and self.start_date and self.start_date.month != self.month:
            errors["start_date"] = (
                f"تاريخ البداية لا يوافق رقم الشهر {self.month}."
            )
        if self.start_date and self.start_date.day != 1:
            errors["start_date"] = "تاريخ بداية الفترة يجب أن يكون أول الشهر."
        if self.month and self.start_date and self.end_date:
            expected_end = _last_day(self.start_date.year, self.month)
            if self.end_date != expected_end:
                errors["end_date"] = (
                    f"تاريخ النهاية يجب أن يكون آخر الشهر ({expected_end})."
                )
        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------- department
class Department(TimeStampedModel):
    """الإدارة / الجهة — optional parent tree (no cycles allowed)."""

    code = models.SlugField("الرمز", max_length=20, unique=True)
    name = models.CharField("الاسم", max_length=150, db_index=True)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="children", verbose_name="الإدارة الأب",
    )
    is_active = models.BooleanField("نشط", default=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        db_table = "departments"
        verbose_name = "إدارة"
        verbose_name_plural = "الإدارات"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def clean(self):
        super().clean()
        if self.parent_id and self.parent_id == self.pk:
            raise ValidationError({"parent": "لا يمكن أن تكون الإدارة أبًا لنفسها."})
        seen, node = set(), self.parent
        while node is not None:
            if node.pk == self.pk:
                raise ValidationError(
                    {"parent": "توجد دورة في الهيكل الإداري (أب ↔ ابن)."}
                )
            if node.pk in seen:
                break
            seen.add(node.pk)
            node = node.parent


# ---------------------------------------------------------------- expense category
class ExpenseCategory(TimeStampedModel):
    """تصنيف المصروفات — referenced by expense accounts (Account.expense_category)."""

    code = models.SlugField("الرمز", max_length=20, unique=True)
    name = models.CharField("الاسم", max_length=150, db_index=True)
    description = models.TextField("الوصف", blank=True)
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        db_table = "expense_categories"
        verbose_name = "تصنيف مصروفات"
        verbose_name_plural = "تصنيفات المصروفات"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


# ---------------------------------------------------------------- chart of accounts
class Account(TimeStampedModel):
    """دليل الحسابات — tree + typed accounts.

    Expense classification = account_type 'expense' + hierarchy (parent)
    + optional link to ExpenseCategory (enforced: only expense accounts).
    """

    TYPE_CHOICES = [
        ("asset", "أصول"),
        ("liability", "التزامات"),
        ("equity", "حقوق ملكية"),
        ("income", "إيرادات"),
        ("expense", "مصروفات"),
    ]

    code = models.SlugField("رقم الحساب", max_length=20, unique=True)
    name = models.CharField("اسم الحساب", max_length=200)
    account_type = models.CharField("نوع الحساب", max_length=12, choices=TYPE_CHOICES)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="children", verbose_name="الحساب الأب",
    )
    expense_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True,
        related_name="accounts", verbose_name="تصنيف المصروف",
        help_text="يُربط فقط بحسابات نوع «مصروفات».",
    )
    is_active = models.BooleanField("نشط", default=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        db_table = "accounts_chart"
        verbose_name = "حساب"
        verbose_name_plural = "دليل الحسابات"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def is_expense(self) -> bool:
        return self.account_type == "expense"

    def clean(self):
        super().clean()
        errors: dict = {}
        if self.parent_id and self.parent_id == self.pk:
            errors["parent"] = "لا يمكن أن يكون الحساب أبًا لنفسه."
        if self.expense_category_id and self.account_type and self.account_type != "expense":
            errors["expense_category"] = (
                "ربط تصنيف المصروف مسموح فقط لحسابات نوع «مصروفات» — "
                "لتصنيف المصروفات بشكل واضح."
            )
        if self.parent and self.account_type and self.parent.account_type != self.account_type:
            errors["parent"] = (
                f"الحساب الأب من نوع «{self.parent.get_account_type_display()}» "
                f"ولا يجوز ربطه بحساب نوع «{self.get_account_type_display()}»."
            )
        seen, node = set(), self.parent
        while node is not None:
            if node.pk == self.pk:
                errors["parent"] = "توجد دورة في شجرة الحسابات (أب ↔ ابن)."
                break
            if node.pk in seen:
                break
            seen.add(node.pk)
            node = node.parent
        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------- supplier
class Supplier(TimeStampedModel):
    """المورّد — master data with contact fields (email/tax validated, unique)."""

    code = models.SlugField("الرمز", max_length=20, unique=True)
    name = models.CharField("اسم المورّد", max_length=200, db_index=True)
    contact_person = models.CharField("مسؤول التواصل", max_length=150, blank=True)
    phone = models.CharField("الهاتف", max_length=40, blank=True)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    tax_number = models.CharField(
        "الرقم الضريبي", max_length=40, blank=True, null=True, unique=True,
    )
    address = models.CharField("العنوان", max_length=255, blank=True)
    is_active = models.BooleanField("نشط", default=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        db_table = "suppliers"
        verbose_name = "مورّد"
        verbose_name_plural = "الموردون"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"
