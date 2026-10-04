"""PHASE 6 — Actual Expenses (المصروفات الفعلية).

Every expense is linked to:
  • Period   (FK — posting rule of PHASE 4 applies: closed ⇒
              periods.post_closed + mandatory audit override)
  • COA      (account must be an expense account — reference.Account)
  • Budget   (via the analysis version's line for (dept, account) —
              computed live by services.expense_budget_context, never stored)
  • Department / Category / Supplier (optional) as business dimensions.

Manual entry with strong validation: required fields, dates inside the
chosen period, positive NUMERIC(14,2) amounts, unique expense number,
duplicate/reference controls, attachment size limit.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.reference.models import Department, ExpenseCategory, FiscalYear, Account, MonthlyPeriod, Supplier


class Expense(models.Model):
    """One actual expense transaction (Synthetic Training Data only)."""

    CURRENCY_CHOICES = [
        ("YER", "ريال يمني (YER)"),
        ("USD", "دولار أمريكي (USD)"),
        ("SAR", "ريال سعودي (SAR)"),
    ]
    PAYMENT_CHOICES = [
        ("cash", "نقدًا"),
        ("transfer", "تحويل بنكي"),
        ("check", "شيك"),
        ("other", "أخرى"),
    ]

    expense_number = models.CharField(
        "رقم المصروف", max_length=30, unique=True, db_index=True, blank=True,
        help_text="يُولَّد تلقائيًا (EXP-سنة-تسلسل) إن تُرك فارغًا.",
    )
    expense_date = models.DateField("تاريخ المصروف")
    period = models.ForeignKey(
        MonthlyPeriod, on_delete=models.PROTECT, related_name="expenses",
        verbose_name="الفترة المحاسبية",
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="expenses",
        verbose_name="الإدارة",
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="expenses",
        verbose_name="الحساب",
    )
    expense_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True,
        related_name="expenses", verbose_name="تصنيف المصروف",
        help_text="يُورَد تلقائيًا من الحساب إن تُرك فارغًا.",
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, null=True, blank=True,
        related_name="expenses", verbose_name="المورّد",
    )
    description = models.TextField("الوصف / البيان")
    amount = models.DecimalField(
        "المبلغ", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    currency = models.CharField(
        "العملة", max_length=3, choices=CURRENCY_CHOICES, default="YER",
    )
    # payment / reference information
    payment_method = models.CharField(
        "طريقة الدفع", max_length=10, choices=PAYMENT_CHOICES,
        default="transfer",
    )
    payment_reference = models.CharField(
        "مرجع الدفع (تحويل/شيك)", max_length=80, blank=True,
    )
    invoice_reference = models.CharField(
        "رقم الفاتورة/المرجع", max_length=80, blank=True, null=True,
        help_text="مرجع المستند — مع المورّد يُشكّل تحكمًا ضد التكرار.",
    )
    # supporting document
    attachment = models.FileField(
        "مستند مرفق", upload_to="expenses/%Y/%m/", blank=True,
        help_text="صورة/PDF للمستند — بحد أقصى 10 ميجابايت.",
    )
    # approval / reference (optional)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expenses_approved", verbose_name="اعتُمد بواسطة",
    )
    approved_at = models.DateTimeField("تاريخ الاعتماد", null=True, blank=True)
    approval_reference = models.CharField(
        "مرجع الاعتماد", max_length=80, blank=True,
    )
    # provenance
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expenses_created", verbose_name="أُنشئ بواسطة",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expenses_updated", verbose_name="عُدّل بواسطة",
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التعديل", auto_now=True)

    class Meta:
        db_table = "expenses"
        verbose_name = "مصروف فعلي"
        verbose_name_plural = "المصروفات الفعلية"
        ordering = ["-expense_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="chk_expense_amount_positive",
            ),
            # duplicate/reference control: one invoice per supplier
            models.UniqueConstraint(
                fields=["supplier", "invoice_reference"],
                condition=models.Q(invoice_reference__isnull=False)
                & ~models.Q(invoice_reference=""),
                name="uq_expense_supplier_invoice",
            ),
        ]

    def __str__(self):
        return f"{self.expense_number} — {self.amount} {self.currency}"

    @property
    def is_approved(self) -> bool:
        return self.approved_by_id is not None or bool(self.approval_reference)

    def clean(self):
        super().clean()
        errors: dict = {}
        # amount strictly positive
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "المبلغ يجب أن يكون موجبًا وأكبر من صفر."
        # date must fall inside the chosen period
        if self.expense_date and self.period_id:
            p = self.period
            if not (p.start_date <= self.expense_date <= p.end_date):
                errors["expense_date"] = (
                    f"التاريخ خارج نطاق الفترة المختارة "
                    f"({p.start_date} — {p.end_date})."
                )
        # COA: expense accounts only (+ active)
        if self.account_id:
            if self.account.account_type != "expense":
                errors["account"] = (
                    "يُسجَّل المصروف على حسابات نوع «مصروفات» فقط — "
                    f"الحساب المحدد «{self.account.get_account_type_display()}»."
                )
            elif not self.account.is_active:
                errors["account"] = "الحساب المحدد غير نشط (معطّل)."
        # department must be active
        if self.department_id and not self.department.is_active:
            errors["department"] = "الإدارة المحددة غير نشطة (معطّل)."
        # supplier (if given) must be active
        if self.supplier_id and not self.supplier.is_active:
            errors["supplier"] = "المورّد المحدد غير نشط (معطّل)."
        # category inherits from the account when blank (same rule as budget lines)
        if not self.expense_category_id and self.account_id:
            self.expense_category = self.account.expense_category
        # duplicate control: identical posting rejected at model level
        if (
            self.expense_date and self.supplier_id and self.amount
            and self.invoice_reference
        ):
            dup = Expense.objects.filter(
                expense_date=self.expense_date,
                supplier_id=self.supplier_id,
                amount=self.amount,
                invoice_reference=self.invoice_reference,
            ).exclude(pk=self.pk)
            if dup.exists():
                errors["invoice_reference"] = (
                    "مصروف مكرر بنفس التاريخ والمورّد والمبلغ والمرجع "
                    f"({dup.first().expense_number})."
                )
        if errors:
            raise ValidationError(errors)
