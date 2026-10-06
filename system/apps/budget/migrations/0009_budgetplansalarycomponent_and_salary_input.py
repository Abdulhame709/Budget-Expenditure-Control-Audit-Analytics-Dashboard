import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("budget", "0008_budgetplanline_advanced_calculation_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="budgetplanline",
            name="input_mode",
            field=models.CharField(
                choices=[
                    ("none", "بدون إدخال"),
                    ("annual", "مبلغ سنوي"),
                    ("monthly", "مبالغ شهرية"),
                    ("quantity_price", "كمية × سعر وحدة"),
                    ("periodic", "مبلغ دوري × عدد الفترات"),
                    ("days_workers", "أيام × عدد العاملين × سعر اليوم"),
                    ("hours_workers", "ساعات × عدد العاملين × سعر الساعة"),
                    ("percentage", "نسبة مئوية من مبلغ أساس"),
                    ("salary_components", "مكونات راتب واستحقاقات موظف"),
                ],
                default="none", max_length=24, verbose_name="طريقة الإدخال",
            ),
        ),
        migrations.CreateModel(
            name="BudgetPlanSalaryComponent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")),
                ("name", models.CharField(max_length=150, verbose_name="اسم المكون")),
                ("component_type", models.CharField(choices=[("earning", "استحقاق / إضافة"), ("deduction", "استقطاع")], default="earning", max_length=16, verbose_name="نوع المكون")),
                ("calculation_method", models.CharField(choices=[("monthly", "مبلغ شهري"), ("percentage", "نسبة من المكونات الأساسية"), ("seasonal", "دفعة موسمية / شهر محدد")], default="monthly", max_length=16, verbose_name="طريقة الحساب")),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)], verbose_name="المبلغ")),
                ("percentage_rate", models.DecimalField(decimal_places=4, default=0, max_digits=7, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name="النسبة المئوية")),
                ("start_month", models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)], verbose_name="شهر البداية")),
                ("periods_count", models.PositiveSmallIntegerField(default=12, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)], verbose_name="عدد الأشهر")),
                ("payment_month", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)], verbose_name="شهر الصرف الموسمي")),
                ("is_percentage_base", models.BooleanField(default=False, help_text="فعّلها للراتب الأساسي أو أي بدل تدخل قيمته في حساب التأمينات والنسب.", verbose_name="يدخل في أساس النسب")),
                ("position", models.PositiveIntegerField(default=1, verbose_name="الترتيب")),
                ("is_active", models.BooleanField(default=True, verbose_name="نشط")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created", to=settings.AUTH_USER_MODEL, verbose_name="أُنشئ بواسطة")),
                ("line", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="salary_components", to="budget.budgetplanline", verbose_name="بند الموظف")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated", to=settings.AUTH_USER_MODEL, verbose_name="عُدّل بواسطة")),
            ],
            options={
                "verbose_name": "مكون راتب لبند الموازنة",
                "verbose_name_plural": "مكونات رواتب بنود الموازنة",
                "db_table": "budget_plan_salary_components",
                "ordering": ["position", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="budgetplansalarycomponent",
            constraint=models.UniqueConstraint(fields=("line", "position"), name="uq_budget_salary_component_position"),
        ),
    ]
