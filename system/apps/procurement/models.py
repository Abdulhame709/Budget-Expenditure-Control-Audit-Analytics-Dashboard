"""PHASE 7 — Procurement Management (المشتريات).

Field set required for the audit test suite (extensible later):
  • supplier information  • department  • date  • description  • amount
  • PO presence/absence   • approval presence/absence
  • quotations count (child model: one offer per supplier)
  • category/account      • supporting document
  • procurement status    • payment/reference information

`services.procurement_audit_context()` is the single entry point the
future procurement audit tests will consume (has_po, has_approval,
quote_count, lowest_quote, has_attachment, …).
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.reference.models import Department, ExpenseCategory, Account, Supplier


class Procurement(models.Model):
    """One procurement record (طلب/ترسية شراء)."""

    STATUS_CHOICES = [
        ("draft", "مسودة"),
        ("pending", "بانتظار الاعتماد"),
        ("approved", "معتمد"),
        ("ordered", "أمر شراء صادر"),
        ("received", "مستلَم"),
        ("cancelled", "ملغى"),
    ]
    PAYMENT_CHOICES = [
        ("cash", "نقدًا"),
        ("transfer", "تحويل بنكي"),
        ("check", "شيك"),
        ("credit", "آجل"),
    ]

    reference_number = models.CharField(
        "رقم السجل", max_length=30, unique=True, db_index=True, blank=True,
        help_text="يُولَّد تلقائيًا (PR-سنة-تسلسل) إن تُرك فارغًا.",
    )
    date = models.DateField("التاريخ")
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="procurements",
        verbose_name="الإدارة",
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="procurements",
        verbose_name="المورّد (الفائز/المرشَّح)",
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="procurements",
        verbose_name="الحساب",
    )
    expense_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True,
        related_name="procurements", verbose_name="تصنيف المصروف",
        help_text="يُورَد تلقائيًا من الحساب إن تُرك فارغًا.",
    )
    description = models.TextField("الوصف / الموضوع")
    amount = models.DecimalField(
        "المبلغ", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    status = models.CharField(
        "حالة المشتريات", max_length=12, choices=STATUS_CHOICES,
        default="draft",
    )
    # purchase order / reference
    purchase_order = models.CharField(
        "رقم أمر الشراء (PO)", max_length=40, blank=True,
        help_text="اتركه فارغًا لاختبار «غياب PO».",
    )
    # approval information
    approval_reference = models.CharField(
        "مرجع الاعتماد", max_length=80, blank=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="procurements_approved", verbose_name="اعتُمد بواسطة",
    )
    approved_at = models.DateTimeField("تاريخ الاعتماد", null=True, blank=True)
    # payment / reference information
    payment_method = models.CharField(
        "طريقة الدفع", max_length=10, choices=PAYMENT_CHOICES, default="transfer",
    )
    payment_reference = models.CharField(
        "مرجع الدفع", max_length=80, blank=True,
    )
    # supporting document
    attachment = models.FileField(
        "مستند مرفق", upload_to="procurements/%Y/%m/", blank=True,
        help_text="مستند الترسية/العرض — بحد أقصى 10 ميجابايت.",
    )
    notes = models.TextField("ملاحظات", blank=True)
    # provenance
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="procurements_created", verbose_name="أُنشئ بواسطة",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="procurements_updated", verbose_name="عُدّل بواسطة",
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التعديل", auto_now=True)

    class Meta:
        db_table = "procurements"
        verbose_name = "سجل مشتريات"
        verbose_name_plural = "سجلات المشتريات"
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="chk_procurement_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.reference_number} — {self.supplier.code}"

    @property
    def has_po(self) -> bool:
        return bool((self.purchase_order or "").strip())

    @property
    def has_approval(self) -> bool:
        return bool((self.approval_reference or "").strip()) or \
            self.approved_by_id is not None

    @property
    def has_attachment(self) -> bool:
        return bool(self.attachment)

    def clean(self):
        super().clean()
        errors: dict = {}
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "المبلغ يجب أن يكون موجبًا وأكبر من صفر."
        if self.account_id:
            if self.account.account_type != "expense":
                errors["account"] = (
                    "يُسجَّل السجل على حسابات نوع «مصروفات» فقط — "
                    f"الحساب المحدد «{self.account.get_account_type_display()}»."
                )
            elif not self.account.is_active:
                errors["account"] = "الحساب المحدد غير نشط (معطّل)."
            elif self.account.level != 5:
                errors["account"] = "يجب اختيار حساب من المستوى الخامس."
        if self.department_id and not self.department.is_active:
            errors["department"] = "الإدارة المحددة غير نشطة (معطّل)."
        if self.supplier_id and not self.supplier.is_active:
            errors["supplier"] = "المورّد المحدد غير نشط (معطّل)."
        if not self.expense_category_id and self.account_id:
            self.expense_category = self.account.expense_category
        if errors:
            raise ValidationError(errors)


class Quotation(models.Model):
    """Supplier offer (عرض سعر) — audit test: عدد عروض الموردين.

    One offer per supplier per procurement (DB-enforced).
    """

    procurement = models.ForeignKey(
        Procurement, on_delete=models.CASCADE, related_name="quotations",
        verbose_name="سجل المشتريات",
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="quotations",
        verbose_name="المورّد",
    )
    amount = models.DecimalField(
        "قيمة العرض", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    offer_date = models.DateField("تاريخ العرض", null=True, blank=True)
    reference = models.CharField("رقم/مرجع العرض", max_length=60, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    created_at = models.DateTimeField("تاريخ الإضافة", auto_now_add=True)

    class Meta:
        db_table = "procurement_quotations"
        verbose_name = "عرض مورّد"
        verbose_name_plural = "عروض الموردين"
        ordering = ["amount"]
        constraints = [
            models.UniqueConstraint(
                fields=["procurement", "supplier"],
                name="uq_quote_per_supplier",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="chk_quote_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.supplier.code}: {self.amount}"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "قيمة العرض يجب أن تكون موجبة."})
        if self.supplier_id and not self.supplier.is_active:
            raise ValidationError({"supplier": "المورّد غير نشط (معطّل)."})
