"""PHASE 5 forms — manual budget entry with Arabic validation."""
from __future__ import annotations

from django import forms

from apps.reference.models import Department, ExpenseCategory, Account, FiscalYear

from .models import MONTH_FIELDS, Budget, BudgetLine, BudgetVersion

AMOUNT_INPUT = forms.NumberInput(
    attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0",
           "dir": "ltr", "style": "min-width:90px"},
)


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["fiscal_year", "name", "notes"]
        widgets = {
            "fiscal_year": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # years without a budget yet (create-time friendly)
        used = Budget.objects.values_list("fiscal_year_id", flat=True)
        self.fields["fiscal_year"].queryset = FiscalYear.objects.exclude(pk__in=used)
        self.fields["fiscal_year"].empty_label = "— اختر السنة المالية —"

    def clean(self):
        super().clean()
        fy = self.cleaned_data.get("fiscal_year")
        if fy and not self.instance.pk:
            if Budget.objects.filter(fiscal_year=fy).exists():
                raise forms.ValidationError(
                    {"fiscal_year": f"توجد ميزانية مسبقة لهذه السنة ({fy})."}
                )
        return self.cleaned_data


class BudgetEditForm(forms.ModelForm):
    """Rename/annotate only — the fiscal year is immutable after creation."""

    class Meta:
        model = Budget
        fields = ["name", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class BudgetVersionForm(forms.ModelForm):
    class Meta:
        model = BudgetVersion
        fields = ["notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class BudgetLineForm(forms.ModelForm):
    class Meta:
        model = BudgetLine
        fields = ["department", "account", "expense_category", *MONTH_FIELDS, "notes"]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "account": forms.Select(attrs={"class": "form-select"}),
            "expense_category": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["department"].empty_label = "— اختر الإدارة —"
        self.fields["account"].queryset = Account.objects.filter(
            account_type="expense", is_active=True
        )
        self.fields["account"].empty_label = "— اختر حساب المصروف —"
        self.fields["expense_category"].queryset = ExpenseCategory.objects.filter(
            is_active=True
        )
        self.fields["expense_category"].required = False
        self.fields["expense_category"].empty_label = "— تُرث من الحساب —"
        for fname in MONTH_FIELDS:
            self.fields[fname].widget = AMOUNT_INPUT
            self.fields[fname].required = False  # empty month ⇒ 0
            self.fields[fname].label = self.instance.__class__._meta.get_field(fname).verbose_name

    def clean(self):
        super().clean()
        # empty months count as zero before the model derives the annual sum
        for fname in MONTH_FIELDS:
            if not self.cleaned_data.get(fname):
                self.cleaned_data[fname] = 0
        return self.cleaned_data
