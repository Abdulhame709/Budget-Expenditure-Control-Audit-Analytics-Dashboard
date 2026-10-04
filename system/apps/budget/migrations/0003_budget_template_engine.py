import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0002_alter_budgetline_version"),
        ("reference", "0002_currency_organization_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BudgetTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")),
                ("name", models.CharField(max_length=180, verbose_name="اسم النموذج")),
                ("description", models.TextField(blank=True, verbose_name="الوصف")),
                ("source_filename", models.CharField(blank=True, max_length=255, verbose_name="اسم الملف المصدر")),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                ("workbook_metadata", models.JSONField(blank=True, default=dict, verbose_name="خصائص المصنف")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created", to=settings.AUTH_USER_MODEL, verbose_name="أُنشئ بواسطة")),
                ("currency", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="budget_templates", to="reference.currency", verbose_name="العملة")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated", to=settings.AUTH_USER_MODEL, verbose_name="عُدّل بواسطة")),
            ],
            options={
                "verbose_name": "نموذج موازنة",
                "verbose_name_plural": "نماذج الموازنة",
                "db_table": "budget_templates",
                "ordering": ["-updated_at", "name"],
            },
        ),
        migrations.CreateModel(
            name="BudgetTemplateSheet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")),
                ("name", models.CharField(max_length=180, verbose_name="اسم الورقة")),
                ("position", models.PositiveSmallIntegerField(default=1, verbose_name="ترتيب الورقة")),
                ("purpose", models.CharField(choices=[("detail", "نموذج تفصيلي"), ("monthly", "توزيع شهري"), ("summary", "إجماليات الحسابات الرئيسية"), ("supporting", "ورقة مساندة")], default="supporting", max_length=20, verbose_name="وظيفة الورقة")),
                ("state", models.CharField(default="visible", max_length=20, verbose_name="حالة الظهور")),
                ("max_row", models.PositiveIntegerField(default=0, verbose_name="عدد الصفوف")),
                ("max_column", models.PositiveIntegerField(default=0, verbose_name="عدد الأعمدة")),
                ("freeze_panes", models.CharField(blank=True, max_length=20, verbose_name="تثبيت الأجزاء")),
                ("merged_ranges", models.JSONField(blank=True, default=list, verbose_name="الخلايا المدمجة")),
                ("layout_metadata", models.JSONField(blank=True, default=dict, verbose_name="خصائص التخطيط")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created", to=settings.AUTH_USER_MODEL, verbose_name="أُنشئ بواسطة")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sheets", to="budget.budgettemplate", verbose_name="النموذج")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated", to=settings.AUTH_USER_MODEL, verbose_name="عُدّل بواسطة")),
            ],
            options={
                "verbose_name": "ورقة نموذج موازنة",
                "verbose_name_plural": "أوراق نماذج الموازنة",
                "db_table": "budget_template_sheets",
                "ordering": ["template", "position"],
            },
        ),
        migrations.CreateModel(
            name="BudgetTemplateColumn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("column_index", models.PositiveIntegerField(verbose_name="رقم العمود")),
                ("column_letter", models.CharField(max_length=5, verbose_name="رمز العمود")),
                ("title", models.CharField(blank=True, max_length=255, verbose_name="عنوان العمود")),
                ("role", models.CharField(choices=[("generic", "عام"), ("account_code", "رقم الحساب"), ("account_name", "اسم الحساب"), ("month_01", "شهر 1"), ("month_02", "شهر 2"), ("month_03", "شهر 3"), ("month_04", "شهر 4"), ("month_05", "شهر 5"), ("month_06", "شهر 6"), ("month_07", "شهر 7"), ("month_08", "شهر 8"), ("month_09", "شهر 9"), ("month_10", "شهر 10"), ("month_11", "شهر 11"), ("month_12", "شهر 12"), ("annual", "الإجمالي السنوي"), ("notes", "ملاحظات")], default="generic", max_length=20, verbose_name="وظيفة العمود")),
                ("width", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="عرض العمود")),
                ("is_hidden", models.BooleanField(default=False, verbose_name="مخفي")),
                ("sheet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="columns", to="budget.budgettemplatesheet", verbose_name="الورقة")),
            ],
            options={
                "verbose_name": "عمود نموذج موازنة",
                "verbose_name_plural": "أعمدة نماذج الموازنة",
                "db_table": "budget_template_columns",
                "ordering": ["sheet", "column_index"],
            },
        ),
        migrations.CreateModel(
            name="BudgetTemplateRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_number", models.PositiveIntegerField(verbose_name="رقم الصف")),
                ("row_type", models.CharField(choices=[("title", "عنوان"), ("header", "رأس جدول"), ("data", "بيانات"), ("subtotal", "إجمالي فرعي"), ("total", "إجمالي"), ("note", "ملاحظة")], default="data", max_length=12, verbose_name="نوع الصف")),
                ("label", models.CharField(blank=True, max_length=500, verbose_name="وصف الصف")),
                ("is_included", models.BooleanField(default=True, verbose_name="يدخل في الموازنة")),
                ("height", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="ارتفاع الصف")),
                ("is_hidden", models.BooleanField(default=False, verbose_name="مخفي")),
                ("account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="budget_template_rows", to="reference.account", verbose_name="الحساب المرتبط")),
                ("sheet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rows", to="budget.budgettemplatesheet", verbose_name="الورقة")),
            ],
            options={
                "verbose_name": "صف نموذج موازنة",
                "verbose_name_plural": "صفوف نماذج الموازنة",
                "db_table": "budget_template_rows",
                "ordering": ["sheet", "row_number"],
            },
        ),
        migrations.CreateModel(
            name="BudgetTemplateCell",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("coordinate", models.CharField(max_length=20, verbose_name="مرجع الخلية")),
                ("raw_value", models.TextField(blank=True, verbose_name="القيمة")),
                ("formula", models.TextField(blank=True, verbose_name="الصيغة")),
                ("data_type", models.CharField(blank=True, max_length=12, verbose_name="نوع البيانات")),
                ("number_format", models.CharField(blank=True, max_length=120, verbose_name="تنسيق الرقم")),
                ("style_metadata", models.JSONField(blank=True, default=dict, verbose_name="خصائص التنسيق")),
                ("column", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cells", to="budget.budgettemplatecolumn", verbose_name="العمود")),
                ("row", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cells", to="budget.budgettemplaterow", verbose_name="الصف")),
            ],
            options={
                "verbose_name": "خلية نموذج موازنة",
                "verbose_name_plural": "خلايا نماذج الموازنة",
                "db_table": "budget_template_cells",
                "ordering": ["row", "column__column_index"],
            },
        ),
        migrations.AddConstraint(
            model_name="budgettemplatesheet",
            constraint=models.UniqueConstraint(fields=("template", "name"), name="uq_budget_template_sheet_name"),
        ),
        migrations.AddConstraint(
            model_name="budgettemplatesheet",
            constraint=models.UniqueConstraint(fields=("template", "position"), name="uq_budget_template_sheet_position"),
        ),
        migrations.AddConstraint(
            model_name="budgettemplatecolumn",
            constraint=models.UniqueConstraint(fields=("sheet", "column_index"), name="uq_budget_template_column"),
        ),
        migrations.AddConstraint(
            model_name="budgettemplaterow",
            constraint=models.UniqueConstraint(fields=("sheet", "row_number"), name="uq_budget_template_row"),
        ),
        migrations.AddConstraint(
            model_name="budgettemplatecell",
            constraint=models.UniqueConstraint(fields=("row", "column"), name="uq_budget_template_cell"),
        ),
    ]
