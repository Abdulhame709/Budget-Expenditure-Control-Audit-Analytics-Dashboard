from django.apps import AppConfig


class AuditRegisterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit_register'
    verbose_name = 'سجل الاستثناءات والملاحظات'
    verbose_name_en = 'Exceptions & Findings Register'
