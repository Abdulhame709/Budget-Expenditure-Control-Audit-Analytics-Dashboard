import decimal

from django.db import migrations


def seed_erp_defaults(apps, schema_editor):
    alias = schema_editor.connection.alias
    Currency = apps.get_model("reference", "Currency")
    OrganizationSettings = apps.get_model("reference", "OrganizationSettings")
    yer, _ = Currency.objects.using(alias).update_or_create(
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
    for code, name_ar, name_en, symbol in (
        ("USD", "دولار أمريكي", "US Dollar", "$"),
        ("SAR", "ريال سعودي", "Saudi Riyal", "ر.س"),
    ):
        Currency.objects.using(alias).get_or_create(
            code=code,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "symbol": symbol,
                "decimal_places": 2,
                "exchange_rate_to_base": decimal.Decimal("1"),
                "is_base": False,
                "is_active": False,
            },
        )
    OrganizationSettings.objects.using(alias).get_or_create(
        pk=1,
        defaults={
            "organization_name_ar": "المنشأة",
            "country": "اليمن",
            "timezone": "Asia/Aden",
            "default_language": "ar",
            "fiscal_year_start_month": 1,
            "base_currency_id": yer.pk,
            "allow_multi_currency": True,
            "date_format": "Y-m-d",
            "thousand_separator": ",",
            "decimal_separator": ".",
        },
    )


class Migration(migrations.Migration):
    dependencies = [("reference", "0002_currency_organization_settings")]
    operations = [migrations.RunPython(seed_erp_defaults, migrations.RunPython.noop)]
