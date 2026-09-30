from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.analytics'
    verbose_name = 'لوحة المؤشرات التحليلية'
    verbose_name_en = 'Analytics Dashboard'
