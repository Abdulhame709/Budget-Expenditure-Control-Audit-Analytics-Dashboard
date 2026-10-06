"""PHASE 5 forms — manual budget entry with Arabic validation."""
from __future__ import annotations

from django import forms

from apps.reference.models import (
    Account,
    Currency,
    Department,
    Employee,
    ExpenseCategory,
    FiscalYear,
)

from .models import (
    MONTH_FIELDS,
    Budget,
    BudgetLine,
    BudgetPlan,
    BudgetPlanLine,
    BudgetPlanSection,
    BudgetTemplate,
    BudgetTemplateRow,
    BudgetTemplateSheet,
    BudgetVersion,
)

AMOUNT_INPUT = forms.NumberInput(
    attrs={"class": "form-control form-control-sm", "step": "0.01", "min": "0",
           "dir": "ltr", "style": "min-width:90px"},
)

MONTH_CHOICES = [(str(month), f"شهر {month}") for month in range(1, 13)]


class BudgetPlanForm(forms.ModelForm):
    class Meta:
        model = BudgetPlan
        fields = ["name", "fiscal_year", "currency", "description", "status", "version"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "fiscal_year": forms.Select(attrs={"class": "form-select"}),
            "currency": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "version": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fiscal_year"].queryset = FiscalYear.objects.filter(is_active=True)
        self.fields["currency"].queryset = Currency.objects.filter(is_active=True)


class BudgetPlanSectionForm(forms.ModelForm):
    class Meta:
        model = BudgetPlanSection
        fields = ["name", "description", "position", "default_main_account"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "position": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "default_main_account": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_main_account"].queryset = Account.objects.filter(
            is_active=True, account_type="expense",
        ).order_by("code")


class BudgetPlanLineForm(forms.ModelForm):
    selected_months = forms.MultipleChoiceField(
        label="الأشهر المختارة", choices=MONTH_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    m01 = forms.DecimalField(label="يناير", required=False, min_value=0, widget=AMOUNT_INPUT)
    m02 = forms.DecimalField(label="فبراير", required=False, min_value=0, widget=AMOUNT_INPUT)
    m03 = forms.DecimalField(label="مارس", required=False, min_value=0, widget=AMOUNT_INPUT)
    m04 = forms.DecimalField(label="أبريل", required=False, min_value=0, widget=AMOUNT_INPUT)
    m05 = forms.DecimalField(label="مايو", required=False, min_value=0, widget=AMOUNT_INPUT)
    m06 = forms.DecimalField(label="يونيو", required=False, min_value=0, widget=AMOUNT_INPUT)
    m07 = forms.DecimalField(label="يوليو", required=False, min_value=0, widget=AMOUNT_INPUT)
    m08 = forms.DecimalField(label="أغسطس", required=False, min_value=0, widget=AMOUNT_INPUT)
    m09 = forms.DecimalField(label="سبتمبر", required=False, min_value=0, widget=AMOUNT_INPUT)
    m10 = forms.DecimalField(label="أكتوبر", required=False, min_value=0, widget=AMOUNT_INPUT)
    m11 = forms.DecimalField(label="نوفمبر", required=False, min_value=0, widget=AMOUNT_INPUT)
    m12 = forms.DecimalField(label="ديسمبر", required=False, min_value=0, widget=AMOUNT_INPUT)

    class Meta:
        model = BudgetPlanLine
        fields = [
            "parent", "position", "row_type", "display_name", "main_account",
            "analytical_account", "department", "employee", "unit_of_measure",
            "input_mode", "distribution_method", "annual_amount", "quantity",
            "unit_price", "periodic_amount", "periods_count", "single_month",
            "selected_months", "aggregate_sections", "estimation_basis", "is_included",
        ]
        widgets = {
            "parent": forms.Select(attrs={"class": "form-select"}),
            "position": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "row_type": forms.Select(attrs={"class": "form-select"}),
            "display_name": forms.TextInput(attrs={"class": "form-control"}),
            "main_account": forms.Select(attrs={"class": "form-select"}),
            "analytical_account": forms.Select(attrs={"class": "form-select"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "employee": forms.Select(attrs={"class": "form-select"}),
            "unit_of_measure": forms.TextInput(attrs={"class": "form-control"}),
            "input_mode": forms.Select(attrs={"class": "form-select"}),
            "distribution_method": forms.Select(attrs={"class": "form-select"}),
            "annual_amount": AMOUNT_INPUT,
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.0001"}),
            "unit_price": AMOUNT_INPUT,
            "periodic_amount": AMOUNT_INPUT,
            "periods_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "single_month": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 12}),
            "aggregate_sections": forms.SelectMultiple(attrs={"class": "form-select", "size": 5}),
            "estimation_basis": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_included": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, section=None, **kwargs):
        self.section = section or getattr(kwargs.get("instance"), "section", None)
        super().__init__(*args, **kwargs)
        expense_accounts = Account.objects.filter(
            is_active=True, account_type="expense",
        ).order_by("code")
        self.fields["main_account"].queryset = expense_accounts
        self.fields["analytical_account"].queryset = expense_accounts
        self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by("code")
        self.fields["employee"].queryset = Employee.objects.filter(is_active=True).order_by("code")
        if self.section:
            self.fields["parent"].queryset = self.section.lines.exclude(
                pk=getattr(self.instance, "pk", None)
            )
            self.fields["aggregate_sections"].queryset = self.section.plan.sections.all()
        if self.instance.pk:
            self.initial["selected_months"] = [str(m) for m in self.instance.selected_months]
            month_map = {row.month: row.amount for row in self.instance.period_amounts.all()}
            for month in range(1, 13):
                self.initial[f"m{month:02d}"] = month_map.get(month, 0)

    def clean_selected_months(self):
        return [int(month) for month in self.cleaned_data.get("selected_months", [])]

    def monthly_values(self):
        return {
            month: self.cleaned_data.get(f"m{month:02d}") or 0
            for month in range(1, 13)
        }

    def clean(self):
        cleaned = super().clean()
        aggregate_sections = cleaned.get("aggregate_sections")
        if aggregate_sections and self.section:
            if aggregate_sections.exclude(plan=self.section.plan).exists():
                self.add_error("aggregate_sections", "يجب اختيار أقسام من النموذج نفسه.")
        if cleaned.get("input_mode") == BudgetPlanLine.INPUT_MONTHLY:
            cleaned["distribution_method"] = BudgetPlanLine.DIST_MANUAL
            cleaned["annual_amount"] = sum(self.monthly_values().values())
            self.instance.distribution_method = BudgetPlanLine.DIST_MANUAL
            self.instance.annual_amount = cleaned["annual_amount"]
        return cleaned


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


class BudgetLineGridForm(forms.ModelForm):
    """Restricted spreadsheet editor: monthly amounts only."""

    class Meta:
        model = BudgetLine
        fields = MONTH_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fname in MONTH_FIELDS:
            self.fields[fname].required = False
            self.fields[fname].widget = forms.NumberInput(attrs={
                "class": "form-control form-control-sm budget-grid-input",
                "step": "0.01",
                "min": "0",
                "dir": "ltr",
                "form": "budget-grid-form",
                "data-month-field": fname,
                "aria-label": self.instance.__class__._meta.get_field(
                    fname
                ).verbose_name,
            })

    def clean(self):
        super().clean()
        for fname in MONTH_FIELDS:
            if self.cleaned_data.get(fname) in (None, ""):
                self.cleaned_data[fname] = 0
        return self.cleaned_data


class BudgetTemplateImportForm(forms.Form):
    name = forms.CharField(
        label="اسم النموذج", max_length=180,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    description = forms.CharField(
        label="الوصف", required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
    workbook = forms.FileField(
        label="ملف Excel",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": ".xlsx,.xlsm"}
        ),
    )

    def clean_workbook(self):
        workbook = self.cleaned_data["workbook"]
        suffix = workbook.name.lower().rsplit(".", 1)[-1]
        if suffix not in {"xlsx", "xlsm"}:
            raise forms.ValidationError("الملفات المدعومة هي XLSX وXLSM فقط.")
        if workbook.size > 25 * 1024 * 1024:
            raise forms.ValidationError("حجم الملف يتجاوز الحد المسموح (25 ميجابايت).")
        return workbook


class BudgetTemplateForm(forms.ModelForm):
    class Meta:
        model = BudgetTemplate
        fields = ["name", "description", "currency", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "currency": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class BudgetTemplateSheetForm(forms.ModelForm):
    class Meta:
        model = BudgetTemplateSheet
        fields = ["purpose"]
        widgets = {"purpose": forms.Select(attrs={"class": "form-select form-select-sm"})}


class BudgetTemplateRowMappingForm(forms.ModelForm):
    class Meta:
        model = BudgetTemplateRow
        fields = ["row_type", "account", "is_included"]
        widgets = {
            "row_type": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "account": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "is_included": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(
            account_type="expense", is_active=True,
        ).order_by("code")
        self.fields["account"].required = False
        self.fields["account"].empty_label = "— غير مربوط —"
