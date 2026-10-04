from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0001_initial"),
        ("reference", "0002_currency_organization_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expense",
            name="currency",
            field=models.CharField(
                choices=[
                    ("YER", "ريال يمني (YER)"),
                    ("USD", "دولار أمريكي (USD)"),
                    ("SAR", "ريال سعودي (SAR)"),
                ],
                default="YER",
                max_length=3,
                verbose_name="العملة",
            ),
        ),
    ]
