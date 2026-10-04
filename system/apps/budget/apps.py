from django.apps import AppConfig


class BudgetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.budget'
    verbose_name = 'الموازنة التقديرية'
    verbose_name_en = 'Budget'
