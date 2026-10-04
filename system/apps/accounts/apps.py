from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'الحسابات والصلاحيات'
    verbose_name_en = 'Accounts & Permissions'
