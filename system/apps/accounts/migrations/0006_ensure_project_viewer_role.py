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


def ensure_viewer_role(apps, schema_editor):
    alias = schema_editor.connection.alias
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")
    role, _ = Role.objects.using(alias).update_or_create(
        code="viewer",
        defaults={
            "name_ar": "مستعرض المشروع",
            "name_en": "Project Viewer",
            "description": "قراءة الوحدات التشغيلية والتقارير والمرفقات دون تعديل أو إدارة.",
            "is_system": True,
        },
    )
    RolePermission.objects.using(alias).filter(role_id=role.pk).delete()
    permission_ids = list(
        Permission.objects.using(alias)
        .filter(code__in=VIEWER_CODES)
        .values_list("pk", flat=True)
    )
    RolePermission.objects.using(alias).bulk_create([
        RolePermission(role_id=role.pk, permission_id=permission_id)
        for permission_id in permission_ids
    ])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_add_project_viewer_role")]
    operations = [migrations.RunPython(ensure_viewer_role, migrations.RunPython.noop)]
