import decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def seed_currency_and_settings(apps, schema_editor):
    Currency = apps.get_model("reference", "Currency")
    OrganizationSettings = apps.get_model("reference", "OrganizationSettings")
    yer, _ = Currency.objects.update_or_create(
        code="YER",
        defaults={
            "name_ar": "ريال يمني",
            "name_en": "Yemeni Rial",
            "symbol": "ر.ي",
            "decimal_places": 2,
            "exchange_rate_to_base": decimal.Decimal("1"),
            "is_base": True,
            "is_active": True,
        },
    )
    Currency.objects.get_or_create(
        code="USD",
        defaults={
            "name_ar": "دولار أمريكي",
            "name_en": "US Dollar",
            "symbol": "$",
            "decimal_places": 2,
            "exchange_rate_to_base": decimal.Decimal("1"),
            "is_base": False,
            "is_active": False,
        },
    )
    Currency.objects.get_or_create(
        code="SAR",
        defaults={
            "name_ar": "ريال سعودي",
            "name_en": "Saudi Riyal",
            "symbol": "ر.س",
            "decimal_places": 2,
            "exchange_rate_to_base": decimal.Decimal("1"),
            "is_base": False,
            "is_active": False,
        },
    )
    OrganizationSettings.objects.get_or_create(
        pk=1,
        defaults={
            "organization_name_ar": "المنشأة",
            "country": "اليمن",
            "timezone": "Asia/Aden",
            "default_language": "ar",
            "fiscal_year_start_month": 1,
            "base_currency": yer,
            "allow_multi_currency": True,
            "date_format": "Y-m-d",
            "thousand_separator": ",",
            "decimal_separator": ".",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("reference", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Currency",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")),
                ("code", models.CharField(max_length=3, unique=True, verbose_name="رمز العملة")),
                ("name_ar", models.CharField(max_length=80, verbose_name="اسم العملة")),
                ("name_en", models.CharField(blank=True, max_length=80, verbose_name="الاسم بالإنجليزية")),
                ("symbol", models.CharField(blank=True, max_length=12, verbose_name="الرمز")),
                ("decimal_places", models.PositiveSmallIntegerField(default=2, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(4)], verbose_name="المنازل العشرية")),
                ("exchange_rate_to_base", models.DecimalField(decimal_places=6, default=decimal.Decimal("1"), max_digits=18, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.000001"))], verbose_name="سعر التحويل إلى العملة الأساسية")),
                ("is_base", models.BooleanField(default=False, verbose_name="العملة الأساسية")),
                ("is_active", models.BooleanField(default=True, verbose_name="نشطة")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created", to=settings.AUTH_USER_MODEL, verbose_name="أُنشئ بواسطة")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated", to=settings.AUTH_USER_MODEL, verbose_name="عُدّل بواسطة")),
            ],
            options={
                "verbose_name": "عملة",
                "verbose_name_plural": "العملات",
                "db_table": "currencies",
                "ordering": ["-is_base", "code"],
            },
        ),
        migrations.AddConstraint(
            model_name="currency",
            constraint=models.UniqueConstraint(fields=("is_base",), condition=Q(("is_base", True)), name="uq_single_base_currency"),
        ),
        migrations.CreateModel(
            name="OrganizationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")),
                ("organization_name_ar", models.CharField(default="المنشأة", max_length=180, verbose_name="اسم المنشأة بالعربية")),
                ("organization_name_en", models.CharField(blank=True, max_length=180, verbose_name="اسم المنشأة بالإنجليزية")),
                ("short_name", models.CharField(blank=True, max_length=80, verbose_name="الاسم المختصر")),
                ("registration_number", models.CharField(blank=True, max_length=80, verbose_name="رقم السجل/الترخيص")),
                ("tax_number", models.CharField(blank=True, max_length=80, verbose_name="الرقم الضريبي")),
                ("country", models.CharField(default="اليمن", max_length=80, verbose_name="الدولة")),
                ("city", models.CharField(blank=True, max_length=80, verbose_name="المدينة")),
                ("address", models.TextField(blank=True, verbose_name="العنوان")),
                ("phone", models.CharField(blank=True, max_length=40, verbose_name="الهاتف")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="البريد الإلكتروني")),
                ("website", models.URLField(blank=True, verbose_name="الموقع الإلكتروني")),
                ("timezone", models.CharField(default="Asia/Aden", max_length=50, verbose_name="المنطقة الزمنية")),
                ("default_language", models.CharField(choices=[("ar", "العربية"), ("en", "English")], default="ar", max_length=5, verbose_name="اللغة الأساسية")),
                ("fiscal_year_start_month", models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)], verbose_name="شهر بداية السنة المالية")),
                ("allow_multi_currency", models.BooleanField(default=True, verbose_name="السماح بتعدد العملات")),
                ("date_format", models.CharField(default="Y-m-d", max_length=20, verbose_name="تنسيق التاريخ")),
                ("thousand_separator", models.CharField(default=",", max_length=3, verbose_name="فاصل الآلاف")),
                ("decimal_separator", models.CharField(default=".", max_length=3, verbose_name="الفاصل العشري")),
                ("base_currency", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="organizations", to="reference.currency", verbose_name="العملة الأساسية")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created", to=settings.AUTH_USER_MODEL, verbose_name="أُنشئ بواسطة")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated", to=settings.AUTH_USER_MODEL, verbose_name="عُدّل بواسطة")),
            ],
            options={
                "verbose_name": "إعدادات المنشأة",
                "verbose_name_plural": "إعدادات المنشأة",
                "db_table": "organization_settings",
            },
        ),
        migrations.RunPython(seed_currency_and_settings, migrations.RunPython.noop),
    ]
