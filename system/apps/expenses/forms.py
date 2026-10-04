"""PHASE 6 forms — manual expense entry with Arabic validation."""
from __future__ import annotations

from django import forms
from django.core.validators import MinValueValidator

from apps.reference.models import Account, Currency, Department, ExpenseCategory, Supplier
from apps.reference.models import MonthlyPeriod

from .models import Expense

MAX_ATTACHMENT_MB = 10

DATE_INPUT = forms.DateInput(attrs={"type": "date", "class": "form-control"})


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "expense_number", "expense_date", "period", "department", "account",
            "expense_category", "supplier", "description", "amount", "currency",
            "payment_method", "payment_reference", "invoice_reference",
            "attachment", "approval_reference",
        ]
        widgets = {
            "expense_number": forms.TextInput(
                attrs={"class": "form-control", "dir": "ltr",
                       "placeholder": "يُولَّد تلقائيًا إن تُرك فارغًا"}),
            "expense_date": DATE_INPUT,
            "period": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "account": forms.Select(attrs={"class": "form-select"}),
            "expense_category": forms.Select(attrs={"class": "form-select"}),
            "supplier": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0.01",
                       "dir": "ltr"}),
            "currency": forms.Select(attrs={"class": "form-select"}),
            "payment_method": forms.Select(attrs={"class": "form-select"}),
            "payment_reference": forms.TextInput(
                attrs={"class": "form-control", "dir": "ltr"}),
            "invoice_reference": forms.TextInput(
                attrs={"class": "form-control", "dir": "ltr"}),
            "attachment": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": ".pdf,.png,.jpg,.jpeg"}),
            "approval_reference": forms.TextInput(
                attrs={"class": "form-control",
                       "placeholder": "اختياري — رقم قرار/خطاب الاعتماد"}),
        }
        labels = {
            "approval_reference": "مرجع الاعتماد (اختياري)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # active dimensions only
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["department"].empty_label = "— اختر الإدارة —"
        self.fields["account"].queryset = Account.objects.filter(
            account_type="expense", is_active=True)
        self.fields["account"].empty_label = "— اختر حساب المصروف —"
        self.fields["expense_category"].queryset = ExpenseCategory.objects.filter(
            is_active=True)
        self.fields["expense_category"].required = False
        self.fields["expense_category"].empty_label = "— تُرث من الحساب —"
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        self.fields["supplier"].required = False
        self.fields["supplier"].empty_label = "— بدون مورّد —"
        self.fields["period"].empty_label = "— اختر الفترة —"
        self.fields["period"].queryset = MonthlyPeriod.objects.select_related(
            "fiscal_year").filter(is_active=True)
        self.fields["expense_number"].required = False
        self.fields["amount"].required = True
        self.fields["amount"].label = "المبلغ"
        self.fields["amount"].validators = [
            MinValueValidator(
                0.01, message="المبلغ يجب أن يكون موجبًا وأكبر من صفر.")
        ]
        currencies = list(Currency.objects.filter(is_active=True).order_by(
            "-is_base", "code"
        ))
        if currencies:
            configured_choices = [
                (currency.code, f"{currency.name_ar} ({currency.code})")
                for currency in currencies
            ]
            configured_codes = {code for code, _label in configured_choices}
            legacy_choices = [
                choice for choice in Expense.CURRENCY_CHOICES
                if choice[0] not in configured_codes
            ]
            self.fields["currency"].choices = configured_choices + legacy_choices
            if not self.instance.pk:
                base = next((currency for currency in currencies if currency.is_base), None)
                if base:
                    self.fields["currency"].initial = base.code
        for name in ("amount", "expense_number", "description", "expense_date",
                     "period", "department", "account", "currency"):
            self.fields[name].error_messages["required"] = "هذا الحقل مطلوب."

    def clean_expense_number(self):
        value = (self.cleaned_data.get("expense_number") or "").strip()
        if value:
            qs = Expense.objects.filter(expense_number=value)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    f"رقم مصروف «{value}» مستخدم مسبقًا — رقم مكرر مرفوض.")
        return value

    def clean_attachment(self):
        upload = self.cleaned_data.get("attachment")
        if upload and hasattr(upload, "size") and upload.size > \
                MAX_ATTACHMENT_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"حجم المرفوق يتجاوز الحد الأقصى ({MAX_ATTACHMENT_MB} ميجابايت).")
        return upload

    def clean(self):
        super().clean()
        # duplicate control (model-level too, but surface it here with Arabic)
        date = self.cleaned_data.get("expense_date")
        supplier = self.cleaned_data.get("supplier")
        amount = self.cleaned_data.get("amount")
        invoice = self.cleaned_data.get("invoice_reference")
        if date and supplier and amount and invoice:
            dup = Expense.objects.filter(
                expense_date=date, supplier=supplier, amount=amount,
                invoice_reference=invoice)
            if self.instance.pk:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                self.add_error(
                    "invoice_reference",
                    "مصروف مكرر بنفس التاريخ والمورّد والمبلغ والمرجع ("
                    + dup.first().expense_number + ").")
        return self.cleaned_data
