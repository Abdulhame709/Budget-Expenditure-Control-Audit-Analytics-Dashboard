"""PHASE 4 forms — Arabic-labelled ModelForms with date widgets.

Cross-field rules live in the models' clean() (runs via ModelForm._post_clean),
so errors always surface in Arabic on the right field.
"""
from __future__ import annotations

from django import forms

from .models import (
    Account,
    Currency,
    Department,
    ExpenseCategory,
    FiscalYear,
    MonthlyPeriod,
    OrganizationSettings,
    Supplier,
)

DATE_INPUT = forms.DateInput(attrs={"type": "date", "class": "form-control"})


class CurrencyForm(forms.ModelForm):
    class Meta:
        model = Currency
        fields = [
            "code", "name_ar", "name_en", "symbol", "decimal_places",
            "exchange_rate_to_base", "is_base", "is_active",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "name_ar": forms.TextInput(attrs={"class": "form-control"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "symbol": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "decimal_places": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 4}),
            "exchange_rate_to_base": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001", "min": "0.000001", "dir": "ltr"}),
            "is_base": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class OrganizationSettingsForm(forms.ModelForm):
    class Meta:
        model = OrganizationSettings
        exclude = ["created_by", "updated_by"]
        widgets = {
            "organization_name_ar": forms.TextInput(attrs={"class": "form-control"}),
            "organization_name_en": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "short_name": forms.TextInput(attrs={"class": "form-control"}),
            "registration_number": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "tax_number": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "phone": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "dir": "ltr"}),
            "website": forms.URLInput(attrs={"class": "form-control", "dir": "ltr"}),
            "timezone": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "default_language": forms.Select(attrs={"class": "form-select"}),
            "fiscal_year_start_month": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 12}),
            "base_currency": forms.Select(attrs={"class": "form-select"}),
            "allow_multi_currency": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "date_format": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "thousand_separator": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "decimal_separator": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["base_currency"].queryset = Currency.objects.filter(is_active=True)


class FiscalYearForm(forms.ModelForm):
    class Meta:
        model = FiscalYear
        fields = ["code", "name", "year", "start_date", "end_date", "is_active", "notes"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "year": forms.NumberInput(attrs={"class": "form-control", "min": 2000, "max": 2100}),
            "start_date": DATE_INPUT,
            "end_date": DATE_INPUT,
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class MonthlyPeriodForm(forms.ModelForm):
    """Status is NOT editable here — open/close happens via the audited
    set-status action on the period detail page."""

    class Meta:
        model = MonthlyPeriod
        fields = ["fiscal_year", "month", "start_date", "end_date", "is_active", "notes"]
        widgets = {
            "fiscal_year": forms.Select(attrs={"class": "form-select"}),
            "month": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 12}),
            "start_date": DATE_INPUT,
            "end_date": DATE_INPUT,
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["code", "name", "parent", "is_active", "notes"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "parent": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["code", "name", "description", "is_active"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["code", "name", "account_type", "parent", "expense_category",
                  "is_active", "notes"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "account_type": forms.Select(attrs={"class": "form-select"}),
            "parent": forms.Select(attrs={"class": "form-select"}),
            "expense_category": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["code", "name", "contact_person", "phone", "email", "tax_number",
                  "address", "is_active", "notes"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "dir": "ltr"}),
            "tax_number": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
