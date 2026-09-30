"""PHASE 7 forms — procurement + quotation entry with Arabic validation."""
from __future__ import annotations

from django import forms
from django.core.validators import MinValueValidator

from apps.reference.models import Department, ExpenseCategory, Account, Supplier

from .models import Procurement, Quotation

MAX_ATTACHMENT_MB = 10

DATE_INPUT = forms.DateInput(attrs={"type": "date", "class": "form-control"})


class ProcurementForm(forms.ModelForm):
    class Meta:
        model = Procurement
        fields = [
            "reference_number", "date", "department", "supplier", "account",
            "expense_category", "description", "amount", "status",
            "purchase_order", "approval_reference", "payment_method",
            "payment_reference", "attachment", "notes",
        ]
        widgets = {
            "reference_number": forms.TextInput(
                attrs={"class": "form-control", "dir": "ltr",
                       "placeholder": "يُولَّد تلقائيًا إن تُرك فارغًا"}),
            "date": DATE_INPUT,
            "department": forms.Select(attrs={"class": "form-select"}),
            "supplier": forms.Select(attrs={"class": "form-select"}),
            "account": forms.Select(attrs={"class": "form-select"}),
            "expense_category": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01",
                       "dir": "ltr"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "purchase_order": forms.TextInput(
                attrs={"class": "form-control", "dir": "ltr",
                       "placeholder": "اتركه فارغًا لغياب PO"}),
            "approval_reference": forms.TextInput(
                attrs={"class": "form-control",
                       "placeholder": "اختياري — رقم قرار الاعتماد"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "payment_reference": forms.TextInput(
                attrs={"class": "form-control", "dir": "ltr"}),
            "attachment": forms.ClearableFileInput(
                attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["department"].empty_label = "— اختر الإدارة —"
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        self.fields["supplier"].empty_label = "— اختر المورّد —"
        self.fields["account"].queryset = Account.objects.filter(
            account_type="expense", is_active=True)
        self.fields["account"].empty_label = "— اختر الحساب —"
        self.fields["expense_category"].queryset = ExpenseCategory.objects.filter(
            is_active=True)
        self.fields["expense_category"].required = False
        self.fields["expense_category"].empty_label = "— تُرث من الحساب —"
        self.fields["reference_number"].required = False
        self.fields["purchase_order"].required = False
        self.fields["amount"].validators = [
            MinValueValidator(0.01, message="المبلغ يجب أن يكون موجبًا وأكبر من صفر.")
        ]
        for name in ("amount", "date", "department", "supplier", "account",
                     "description"):
            self.fields[name].error_messages["required"] = "هذا الحقل مطلوب."

    def clean_reference_number(self):
        value = (self.cleaned_data.get("reference_number") or "").strip()
        if value:
            qs = Procurement.objects.filter(reference_number=value)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f"رقم سجل «{value}» مستخدم مسبقًا — رقم مكرر مرفوض.")
        return value

    def clean_attachment(self):
        upload = self.cleaned_data.get("attachment")
        if upload and hasattr(upload, "size") and upload.size > \
                MAX_ATTACHMENT_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"حجم المرفوق يتجاوز الحد الأقصى ({MAX_ATTACHMENT_MB} ميجابايت).")
        return upload


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ["supplier", "amount", "offer_date", "reference", "notes"]
        widgets = {
            "supplier": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01",
                       "dir": "ltr"}),
            "offer_date": DATE_INPUT,
            "reference": forms.TextInput(
                attrs={"class": "form-control", "dir": "ltr"}),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, procurement=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.procurement = procurement
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        self.fields["supplier"].empty_label = "— اختر المورّد —"
        self.fields["supplier"].required = True
        self.fields["amount"].validators = [
            MinValueValidator(0.01, message="قيمة العرض يجب أن تكون موجبة.")
        ]
        self.fields["amount"].error_messages["required"] = "هذا الحقل مطلوب."

    def clean_supplier(self):
        supplier = self.cleaned_data.get("supplier")
        if supplier and self.procurement is not None:
            qs = Quotation.objects.filter(
                procurement=self.procurement, supplier=supplier)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "لدى هذا المورّد عرض مسجَّل مسبقًا على نفس السجل "
                    "(عرض واحد لكل مورّد).")
        return supplier
