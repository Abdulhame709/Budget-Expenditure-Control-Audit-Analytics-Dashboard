"""PHASE 5 forms — manual budget entry with Arabic validation."""
from __future__ import annotations

from django import forms
from django.forms import modelformset_factory

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
    BudgetPlanSalaryComponent,
    BudgetPlanSection,
    BudgetTemplate,
    BudgetTemplateColumn,
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
        fields = ["department", "name", "description", "position", "default_main_account"]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "position": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "default_main_account": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, plan=None, **kwargs):
        self.plan = plan or getattr(kwargs.get("instance"), "plan", None)
        super().__init__(*args, **kwargs)
        if self.plan:
            self.instance.plan = self.plan
        self.fields["department"].queryset = Department.objects.filter(
            is_active=True,
        ).select_related("parent").order_by("code")
        self.fields["department"].required = True
        self.fields["department"].empty_label = "— اختر من الهيكل التنظيمي —"
        self.fields["name"].required = False
        self.fields["name"].help_text = "اختياري؛ عند تركه فارغًا يُستخدم اسم الإدارة/القسم التنظيمي."
        self.fields["default_main_account"].queryset = Account.objects.operational().filter(
            account_type="expense",
        ).order_by("code")
        self.fields["default_main_account"].label = "الحساب الرئيسي الافتراضي (المستوى 5)"

    def clean(self):
        cleaned = super().clean()
        department = cleaned.get("department")
        if department and not (cleaned.get("name") or "").strip():
            cleaned["name"] = department.name
            self.instance.name = department.name
        return cleaned


class BudgetPlanParentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.position}. {obj.display_name} — {obj.get_row_type_display()}"


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
            "days_count", "hours_count", "workers_count", "rate_amount",
            "base_amount", "percentage_rate",
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
            "days_count": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "hours_count": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "workers_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "rate_amount": AMOUNT_INPUT,
            "base_amount": AMOUNT_INPUT,
            "percentage_rate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.0001"}),
            "single_month": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 12}),
            "aggregate_sections": forms.SelectMultiple(attrs={"class": "form-select", "size": 5}),
            "estimation_basis": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_included": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, section=None, **kwargs):
        self.section = section or getattr(kwargs.get("instance"), "section", None)
        super().__init__(*args, **kwargs)
        self.fields["parent"] = BudgetPlanParentChoiceField(
            queryset=BudgetPlanLine.objects.none(), required=False,
            label="يتبع للبند / المجموعة",
            empty_label="— بند مستقل (بدون أب) —",
            help_text="اختياري: اختر بندًا محفوظًا من القسم نفسه لتجميع البنود في شكل شجرة.",
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        for field_name in (
            "days_count", "hours_count", "workers_count", "rate_amount",
            "base_amount", "percentage_rate",
        ):
            self.fields[field_name].required = False
        main_accounts = Account.objects.main_accounts().filter(
            account_type="expense",
        ).order_by("code")
        self.fields["main_account"].queryset = main_accounts
        self.fields["main_account"].label = "الحساب الرئيسي (المستوى 5)"
        main_id = (
            self.data.get("main_account")
            if self.is_bound else getattr(self.instance, "main_account_id", None)
        )
        analytical_accounts = Account.objects.none()
        if str(main_id or "").isdigit():
            analytical_accounts = Account.objects.analytical_for(main_id).filter(
                account_type="expense",
            ).order_by("code")
        self.fields["analytical_account"].queryset = analytical_accounts
        self.fields["analytical_account"].label = "الحساب التحليلي (المستوى 6)"
        self.fields["analytical_account"].empty_label = "— اختر حسابًا تابعًا للرئيسي —"
        departments = Department.objects.filter(is_active=True).order_by("code")
        employees = Employee.objects.filter(is_active=True).order_by("code")
        if self.section and self.section.department_id:
            departments = departments.filter(pk=self.section.department_id)
            employees = employees.filter(department_id=self.section.department_id)
            self.fields["department"].initial = self.section.department_id
            self.fields["department"].disabled = True
            self.fields["department"].help_text = (
                "موروثة تلقائيًا من قسم نموذج الموازنة المرتبط بالهيكل التنظيمي."
            )
        self.fields["department"].queryset = departments
        self.fields["employee"].queryset = employees
        if self.section:
            parent_queryset = self.section.lines.exclude(
                pk=getattr(self.instance, "pk", None),
            )
            self.fields["parent"].queryset = parent_queryset.order_by("position", "pk")
            self.fields["aggregate_sections"].queryset = self.section.plan.sections.all()
            if not self.is_bound and not self.instance.pk:
                last_position = self.section.lines.order_by("-position").values_list(
                    "position", flat=True,
                ).first()
                self.fields["position"].initial = (last_position or 0) + 1
                if self.section.default_main_account_id:
                    self.fields["main_account"].initial = self.section.default_main_account_id
        if self.instance.pk:
            self.fields["parent"].initial = self.instance.parent_id
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
        row_type = cleaned.get("row_type")
        input_mode = cleaned.get("input_mode")
        input_row_types = {
            BudgetPlanLine.TYPE_ANALYTICAL_ACCOUNT,
            BudgetPlanLine.TYPE_DETAIL,
        }
        account_row_types = {
            BudgetPlanLine.TYPE_MAIN_ACCOUNT,
            BudgetPlanLine.TYPE_ANALYTICAL_ACCOUNT,
            BudgetPlanLine.TYPE_DETAIL,
        }
        total_row_types = {
            BudgetPlanLine.TYPE_SUBTOTAL,
            BudgetPlanLine.TYPE_TOTAL,
        }

        if row_type not in account_row_types:
            cleaned["main_account"] = None
            cleaned["analytical_account"] = None
        elif row_type == BudgetPlanLine.TYPE_MAIN_ACCOUNT:
            cleaned["analytical_account"] = None
            if not cleaned.get("main_account"):
                self.add_error("main_account", "اختر الحساب الرئيسي لهذا الصف.")
        elif not cleaned.get("main_account"):
            self.add_error("main_account", "اختر الحساب الرئيسي أولًا.")
        elif not cleaned.get("analytical_account"):
            self.add_error("analytical_account", "اختر الحساب التحليلي التابع للحساب الرئيسي.")

        if row_type != BudgetPlanLine.TYPE_DETAIL:
            cleaned["employee"] = None
        if row_type not in total_row_types:
            cleaned["aggregate_sections"] = BudgetPlanSection.objects.none()

        if row_type not in input_row_types:
            cleaned["input_mode"] = BudgetPlanLine.INPUT_NONE
            cleaned["distribution_method"] = BudgetPlanLine.DIST_NONE
            cleaned["annual_amount"] = 0
            cleaned["quantity"] = 0
            cleaned["unit_price"] = 0
            cleaned["periodic_amount"] = 0
            cleaned["periods_count"] = 0
            cleaned["days_count"] = 0
            cleaned["hours_count"] = 0
            cleaned["workers_count"] = 0
            cleaned["rate_amount"] = 0
            cleaned["base_amount"] = 0
            cleaned["percentage_rate"] = 0
            cleaned["single_month"] = None
            cleaned["selected_months"] = []
            input_mode = BudgetPlanLine.INPUT_NONE

        aggregate_sections = cleaned.get("aggregate_sections")
        if aggregate_sections and self.section:
            if aggregate_sections.exclude(plan=self.section.plan).exists():
                self.add_error("aggregate_sections", "يجب اختيار أقسام من النموذج نفسه.")
        if input_mode == BudgetPlanLine.INPUT_MONTHLY:
            cleaned["distribution_method"] = BudgetPlanLine.DIST_MANUAL
            cleaned["annual_amount"] = sum(self.monthly_values().values())
            self.instance.distribution_method = BudgetPlanLine.DIST_MANUAL
            self.instance.annual_amount = cleaned["annual_amount"]
        elif input_mode == BudgetPlanLine.INPUT_NONE:
            cleaned["distribution_method"] = BudgetPlanLine.DIST_NONE
            cleaned["annual_amount"] = 0
        elif input_mode == BudgetPlanLine.INPUT_SALARY_COMPONENTS:
            cleaned["distribution_method"] = BudgetPlanLine.DIST_NONE
            cleaned["annual_amount"] = 0
            if row_type != BudgetPlanLine.TYPE_DETAIL:
                self.add_error("row_type", "مكونات الراتب تستخدم مع صف تفصيلي مرتبط بموظف.")
            if not cleaned.get("employee"):
                self.add_error("employee", "اختر الموظف المرتبط بمكونات الراتب.")
        if input_mode != BudgetPlanLine.INPUT_QUANTITY_PRICE:
            cleaned["quantity"] = 0
            cleaned["unit_price"] = 0
        if input_mode != BudgetPlanLine.INPUT_PERIODIC:
            cleaned["periodic_amount"] = 0
            cleaned["periods_count"] = 0
        if input_mode != BudgetPlanLine.INPUT_DAYS_WORKERS:
            cleaned["days_count"] = 0
        if input_mode != BudgetPlanLine.INPUT_HOURS_WORKERS:
            cleaned["hours_count"] = 0
        if input_mode not in {
            BudgetPlanLine.INPUT_DAYS_WORKERS,
            BudgetPlanLine.INPUT_HOURS_WORKERS,
        }:
            cleaned["workers_count"] = 0
            cleaned["rate_amount"] = 0
        if input_mode != BudgetPlanLine.INPUT_PERCENTAGE:
            cleaned["base_amount"] = 0
            cleaned["percentage_rate"] = 0
        distribution_method = cleaned.get("distribution_method")
        if distribution_method != BudgetPlanLine.DIST_SINGLE_MONTH:
            cleaned["single_month"] = None
        if distribution_method != BudgetPlanLine.DIST_SELECTED_MONTHS:
            cleaned["selected_months"] = []
        return cleaned


class BudgetPlanBulkLineForm(forms.ModelForm):
    """Compact editor used to review and save several section lines at once."""

    class Meta:
        model = BudgetPlanLine
        fields = [
            "position", "row_type", "display_name", "main_account",
            "analytical_account", "input_mode", "distribution_method",
            "annual_amount", "estimation_basis", "is_included",
        ]
        widgets = {
            "position": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 1}),
            "row_type": forms.Select(attrs={"class": "form-select form-select-sm js-row-type"}),
            "display_name": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "اسم البند"}),
            "main_account": forms.Select(attrs={"class": "form-select form-select-sm js-main-account"}),
            "analytical_account": forms.Select(attrs={"class": "form-select form-select-sm js-analytical-account"}),
            "input_mode": forms.Select(attrs={"class": "form-select form-select-sm js-input-mode"}),
            "distribution_method": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "annual_amount": AMOUNT_INPUT,
            "estimation_basis": forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "ملاحظة أو أساس التقدير"}),
            "is_included": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, section=None, **kwargs):
        self.section = section
        super().__init__(*args, **kwargs)
        self.fields["main_account"].queryset = Account.objects.main_accounts().filter(
            account_type="expense",
        ).order_by("code")
        main_account_id = None
        if self.is_bound:
            main_account_id = self.data.get(self.add_prefix("main_account"))
        elif self.instance.pk:
            main_account_id = self.instance.main_account_id
        else:
            initial_account = self.initial.get("main_account")
            main_account_id = getattr(initial_account, "pk", initial_account)
            if not main_account_id and self.section and self.section.default_main_account_id:
                main_account_id = self.section.default_main_account_id
                self.initial["main_account"] = main_account_id
        analytical_accounts = Account.objects.none()
        if str(main_account_id or "").isdigit():
            analytical_accounts = Account.objects.analytical_for(int(main_account_id)).filter(
                account_type="expense",
            ).order_by("code")
        self.fields["analytical_account"].queryset = analytical_accounts
        self.fields["main_account"].empty_label = "— الحساب الرئيسي —"
        self.fields["analytical_account"].empty_label = "— الحساب التحليلي —"
        self.fields["input_mode"].choices = [
            (BudgetPlanLine.INPUT_NONE, "بدون إدخال"),
            (BudgetPlanLine.INPUT_ANNUAL, "مبلغ سنوي"),
        ]
        self.fields["distribution_method"].choices = [
            (BudgetPlanLine.DIST_NONE, "بدون توزيع"),
            (BudgetPlanLine.DIST_EQUAL, "متساوٍ على 12 شهرًا"),
            (BudgetPlanLine.DIST_SINGLE_MONTH, "شهر واحد (يستكمل من شاشة البند)"),
        ]

    def clean(self):
        cleaned = super().clean()
        row_type = cleaned.get("row_type")
        input_rows = {
            BudgetPlanLine.TYPE_ANALYTICAL_ACCOUNT,
            BudgetPlanLine.TYPE_DETAIL,
        }
        if row_type == BudgetPlanLine.TYPE_MAIN_ACCOUNT:
            cleaned["analytical_account"] = None
            cleaned["input_mode"] = BudgetPlanLine.INPUT_NONE
            cleaned["distribution_method"] = BudgetPlanLine.DIST_NONE
            cleaned["annual_amount"] = 0
            if not cleaned.get("main_account"):
                self.add_error("main_account", "اختر الحساب الرئيسي.")
        elif row_type in input_rows:
            if not cleaned.get("main_account"):
                self.add_error("main_account", "اختر الحساب الرئيسي.")
            if not cleaned.get("analytical_account"):
                self.add_error("analytical_account", "اختر الحساب التحليلي التابع له.")
            if cleaned.get("input_mode") == BudgetPlanLine.INPUT_NONE:
                cleaned["annual_amount"] = 0
                cleaned["distribution_method"] = BudgetPlanLine.DIST_NONE
            elif cleaned.get("distribution_method") == BudgetPlanLine.DIST_NONE:
                cleaned["distribution_method"] = BudgetPlanLine.DIST_EQUAL
        else:
            cleaned["main_account"] = None
            cleaned["analytical_account"] = None
            cleaned["input_mode"] = BudgetPlanLine.INPUT_NONE
            cleaned["distribution_method"] = BudgetPlanLine.DIST_NONE
            cleaned["annual_amount"] = 0
        return cleaned

    def validate_unique(self):
        # The formset validates duplicate positions across all submitted rows.
        # Skipping the per-form database lookup also permits swapping positions
        # because the view temporarily moves stored positions before saving.
        return None


def budget_plan_bulk_line_formset(*, extra=5):
    return modelformset_factory(
        BudgetPlanLine,
        form=BudgetPlanBulkLineForm,
        extra=extra,
        can_delete=True,
    )


class BudgetPlanSalaryComponentForm(forms.ModelForm):
    class Meta:
        model = BudgetPlanSalaryComponent
        fields = [
            "position", "name", "component_type", "calculation_method",
            "amount", "percentage_rate", "start_month", "periods_count",
            "payment_month", "is_percentage_base", "is_active",
        ]
        widgets = {
            "position": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 1}),
            "name": forms.TextInput(attrs={"class": "form-control form-control-sm"}),
            "component_type": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "calculation_method": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "amount": AMOUNT_INPUT,
            "percentage_rate": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 0, "max": 100, "step": "0.0001"}),
            "start_month": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 1, "max": 12}),
            "periods_count": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 1, "max": 12}),
            "payment_month": forms.NumberInput(attrs={"class": "form-control form-control-sm", "min": 1, "max": 12}),
            "is_percentage_base": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("amount", "percentage_rate", "payment_month"):
            self.fields[field_name].required = False

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("calculation_method")
        if method == BudgetPlanSalaryComponent.METHOD_MONTHLY:
            cleaned["percentage_rate"] = 0
            cleaned["payment_month"] = None
        elif method == BudgetPlanSalaryComponent.METHOD_PERCENTAGE:
            cleaned["amount"] = 0
            cleaned["start_month"] = 1
            cleaned["periods_count"] = 12
            cleaned["payment_month"] = None
        elif method == BudgetPlanSalaryComponent.METHOD_SEASONAL:
            cleaned["percentage_rate"] = 0
            cleaned["start_month"] = 1
            cleaned["periods_count"] = 1
            cleaned["is_percentage_base"] = False
        return cleaned


BudgetPlanSalaryComponentFormSet = forms.inlineformset_factory(
    BudgetPlanLine,
    BudgetPlanSalaryComponent,
    form=BudgetPlanSalaryComponentForm,
    extra=1,
    can_delete=True,
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
        fields = [
            "department", "account", "analytical_account", "expense_category",
            *MONTH_FIELDS, "notes",
        ]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "account": forms.Select(attrs={"class": "form-select"}),
            "analytical_account": forms.Select(attrs={"class": "form-select"}),
            "expense_category": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["department"].empty_label = "— اختر الإدارة —"
        self.fields["account"].queryset = Account.objects.main_accounts().filter(
            account_type="expense"
        )
        self.fields["account"].label = "الحساب الرئيسي (المستوى 5)"
        self.fields["account"].empty_label = "— اختر الحساب الرئيسي —"
        main_id = (
            self.data.get("account")
            if self.is_bound else getattr(self.instance, "account_id", None)
        )
        analytical_accounts = Account.objects.none()
        if str(main_id or "").isdigit():
            analytical_accounts = Account.objects.analytical_for(main_id).filter(
                account_type="expense",
            ).order_by("code")
        self.fields["analytical_account"].queryset = analytical_accounts
        self.fields["analytical_account"].label = "الحساب التحليلي (المستوى 6)"
        self.fields["analytical_account"].empty_label = "— اختر حسابًا تابعًا للرئيسي —"
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


class BudgetTemplateRefreshForm(forms.Form):
    workbook = forms.FileField(
        label="نسخة Excel الجديدة",
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
        fields = ["row_type", "label", "main_account", "analytical_account", "is_included"]
        widgets = {
            "row_type": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "label": forms.TextInput(attrs={
                "class": "form-control form-control-sm js-template-row-label",
                "placeholder": "اكتب عنوان الصف أو بيان الإجمالي",
            }),
            "main_account": forms.Select(attrs={"class": "form-select form-select-sm js-template-main"}),
            "analytical_account": forms.Select(attrs={"class": "form-select form-select-sm js-template-analytical"}),
            "is_included": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["main_account"].queryset = Account.objects.main_accounts().filter(
            account_type="expense",
        ).order_by("code")
        self.fields["main_account"].required = False
        self.fields["main_account"].empty_label = "— رئيسي مستوى 5 —"
        main_id = (
            self.data.get(self.add_prefix("main_account"))
            if self.is_bound else self.instance.main_account_id
        )
        analytical = Account.objects.none()
        if str(main_id or "").isdigit():
            analytical = Account.objects.analytical_for(main_id).filter(
                account_type="expense",
            ).order_by("code")
        self.fields["analytical_account"].queryset = analytical
        self.fields["analytical_account"].required = False
        self.fields["analytical_account"].empty_label = "— تحليلي مستوى 6 —"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("row_type") != BudgetTemplateRow.TYPE_DATA:
            cleaned["main_account"] = None
            cleaned["analytical_account"] = None
            cleaned["is_included"] = False
        return cleaned


class BudgetTemplateColumnRoleForm(forms.ModelForm):
    class Meta:
        model = BudgetTemplateColumn
        fields = ["role"]
        widgets = {"role": forms.Select(attrs={"class": "form-select form-select-sm"})}
