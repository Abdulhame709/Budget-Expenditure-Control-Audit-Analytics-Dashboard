from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.expenses'
    verbose_name = 'المصروفات الفعلية'
    verbose_name_en = 'Actual Expenses'
