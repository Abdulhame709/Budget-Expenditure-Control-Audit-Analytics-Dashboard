"""PHASE 4 — add `periods.post_closed` (closed-period posting override).

Source of truth: apps.accounts.permissions (PERMISSIONS / ROLES).
Forward: sync the catalog and ensure the admin role holds the new code.
Backward: remove the new code and its grants only.
"""
from django.db import migrations


NEW_CODE = "periods.post_closed"


def seed_phase4(apps, schema_editor):
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

    # grant the new code to every role the approved matrix gives it to
    for rcode, spec in ROLES.items():
        if NEW_CODE not in spec["permissions"]:
            continue
        role = Role.objects.filter(code=rcode).first()
        if role:
            RolePermission.objects.get_or_create(
                role=role, permission=perm_objs[NEW_CODE]
            )


def unseed_phase4(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code=NEW_CODE).delete()  # cascades grants


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_seed_rbac"),
    ]
    operations = [
        migrations.RunPython(seed_phase4, unseed_phase4),
    ]
