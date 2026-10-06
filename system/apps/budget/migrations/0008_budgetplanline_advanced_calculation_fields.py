from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0007_remove_budgetline_uq_budget_line_and_more"),
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
                ],
                default="none",
                max_length=24,
                verbose_name="طريقة الإدخال",
            ),
        ),
        migrations.AddField(
            model_name="budgetplanline",
            name="days_count",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[MinValueValidator(0)], verbose_name="عدد الأيام"),
        ),
        migrations.AddField(
            model_name="budgetplanline",
            name="hours_count",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[MinValueValidator(0)], verbose_name="عدد الساعات"),
        ),
        migrations.AddField(
            model_name="budgetplanline",
            name="workers_count",
            field=models.PositiveIntegerField(default=0, verbose_name="عدد العاملين"),
        ),
        migrations.AddField(
            model_name="budgetplanline",
            name="rate_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[MinValueValidator(0)], verbose_name="سعر اليوم / الساعة"),
        ),
        migrations.AddField(
            model_name="budgetplanline",
            name="base_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[MinValueValidator(0)], verbose_name="مبلغ الأساس"),
        ),
        migrations.AddField(
            model_name="budgetplanline",
            name="percentage_rate",
            field=models.DecimalField(decimal_places=4, default=0, max_digits=7, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="النسبة المئوية"),
        ),
    ]
