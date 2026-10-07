import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0009_budgetplansalarycomponent_and_salary_input"),
        ("reference", "0004_employee"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgettemplaterow",
            name="main_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="budget_template_main_rows",
                to="reference.account",
                verbose_name="الحساب الرئيسي",
            ),
        ),
        migrations.AddField(
            model_name="budgettemplaterow",
            name="analytical_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="budget_template_analytical_rows",
                to="reference.account",
                verbose_name="الحساب التحليلي",
            ),
        ),
        migrations.AddField(
            model_name="budgettemplatecell",
            name="override_value",
            field=models.TextField(
                blank=True,
                help_text="تظل القيمة الأصلية محفوظة ويمكن الرجوع إليها بإزالة التعديل.",
                null=True,
                verbose_name="القيمة المعدلة",
            ),
        ),
        migrations.AddField(
            model_name="budgettemplatecell",
            name="is_editable",
            field=models.BooleanField(default=False, verbose_name="قابلة للتحرير"),
        ),
    ]
