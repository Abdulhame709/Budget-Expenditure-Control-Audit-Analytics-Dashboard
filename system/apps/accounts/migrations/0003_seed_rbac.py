"""Seed the RBAC catalog: 23 permission codes + the 4 approved roles + grants.

System catalog (like a reference table), not business seed data.
Source of truth: apps.accounts.permissions (PERMISSIONS / ROLES).
"""
from django.db import migrations


def seed_rbac(apps, schema_editor):
    from apps.accounts.permissions import PERMISSIONS, ROLES

    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    perm_objs = {}
    for code, (module, label) in PERMISSIONS.items():
        obj, _ = Permission.objects.update_or_create(
            code=code, defaults={"module": module, "label_ar": label}
        )
        perm_objs[code] = obj

    for rcode, spec in ROLES.items():
        role, _ = Role.objects.update_or_create(
            code=rcode,
            defaults={
                "name_ar": spec["name_ar"],
                "name_en": spec["name_en"],
                "description": spec["description"],
                "is_system": True,
            },
        )
        for pcode in spec["permissions"]:
            RolePermission.objects.update_or_create(role=role, permission=perm_objs[pcode])


def unseed_rbac(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")
    RolePermission.objects.filter(role__is_system=True).delete()
    Role.objects.filter(is_system=True).delete()
    Permission.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_permission_role_rolepermission_userrole"),
    ]
    operations = [
        migrations.RunPython(seed_rbac, unseed_rbac),
    ]
