from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("imports", "0005_detailedbudgetsheet_display_title"),
    ]

    operations = [
        migrations.AlterField(
            model_name="importjob",
            name="target",
            field=models.CharField(
                choices=[
                    ("fiscal_years", "السنوات المالية"),
                    ("periods", "الفترات الشهرية"),
                    ("departments", "الإدارات"),
                    ("expense_categories", "تصنيفات المصروفات"),
                    ("accounts", "الدليل المحاسبي"),
                    ("suppliers", "الموردون"),
                    ("budget_lines", "الموازنة التقديرية — السطور الشهرية"),
                    ("budget_matrix", "الموازنة التقديرية — حسابات مستوى 5 و6 / مستوى 5 فقط"),
                    ("actual_matrix", "المصروفات الفعلية — إجمالي شهر واحد حسب الحساب"),
                    ("detailed_budget", "الموازنة التفصيلية الأولية (أوراق متعددة)"),
                    ("expenses", "المصروفات الفعلية"),
                    ("procurements", "سجلات المشتريات"),
                    ("quotations", "عروض أسعار الموردين"),
                ],
                default="expenses", max_length=30, verbose_name="الهدف",
            ),
        ),
    ]
