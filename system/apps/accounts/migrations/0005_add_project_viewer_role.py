from django.db import migrations


VIEWER_CODES = (
    "dashboard.view",
    "reference.view",
    "budget.view",
    "expenses.view",
    "procurement.view",
    "imports.view",
    "audit.view",
    "exceptions.view",
    "risk.view",
    "findings.view",
    "reports.view",
    "attachments.view",
)


def add_viewer_role(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")

    role, _ = Role.objects.update_or_create(
        code="viewer",
        defaults={
            "name_ar": "مستعرض المشروع",
            "name_en": "Project Viewer",
            "description": "قراءة الوحدات التشغيلية والتقارير والمرفقات دون تعديل أو إدارة.",
            "is_system": True,
        },
    )
    RolePermission.objects.filter(role=role).delete()
    permissions = Permission.objects.filter(code__in=VIEWER_CODES)
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=permission) for permission in permissions]
    )


def remove_viewer_role(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(code="viewer").delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_seed_periods_permission")]
    operations = [migrations.RunPython(add_viewer_role, remove_viewer_role)]
