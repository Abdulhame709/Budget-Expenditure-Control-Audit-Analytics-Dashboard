"""User management services — authorization + object rules + audit logging live here.

Every sensitive mutation goes through these functions (views never write
UserRole rows directly), so enforcement cannot be "forgotten" in a view.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import has_perm
from apps.governance.services import log_action

User = get_user_model()


def _role_codes(user) -> list[str]:
    return sorted(
        UserRole.objects.filter(user=user).values_list("role__code", flat=True)
    )


@transaction.atomic
def create_user(
    *,
    actor,
    username: str,
    password: str,
    full_name: str = "",
    job_title: str = "",
    role_codes: list[str] | tuple = (),
    is_demo: bool = False,
    request=None,
):
    """Create a user + assign roles. Page/Action permission: users.manage."""
    if not has_perm(actor, "users.manage"):
        raise PermissionDenied("إنشاء المستخدمين يتطلب صلاحية users.manage")
    if settings.DEPLOYMENT_ENV == "production" and is_demo:
        raise ValidationError("إنشاء حساب تدريبي غير مسموح في الإنتاج.")
    if User.objects.filter(username=username).exists():
        raise ValidationError({"username": "اسم المستخدم موجود مسبقًا"})

    user = User(
        username=username,
        full_name=full_name,
        job_title=job_title,
        is_demo=is_demo,
    )
    user.set_password(password)  # hashed (PBKDF2) — never stored, never logged
    user.save()

    roles = list(Role.objects.filter(code__in=list(role_codes)))
    UserRole.objects.bulk_create(
        [UserRole(user=user, role=r, assigned_by=actor) for r in roles]
    )

    log_action(
        action="user_created",
        entity_type="user",
        entity_id=user.pk,
        diff={
            "username": username,
            "full_name": full_name,
            "job_title": job_title,
            "is_demo": is_demo,
            "roles": [r.code for r in roles],
        },
        request=request,
        actor=actor,
    )
    return user


# Default role for self-service signups — read-only project access.
SELF_REGISTER_ROLE = "management"


@transaction.atomic
def register_user(*, email: str, password: str, full_name: str = "", request=None):
    """Self-service signup. No permission gate (the user does not exist yet).

    The new account always joins the read-only «management» role; an admin can
    later elevate the account from the users screen. Username == email (login form
    accepts either).
    """
    email = (email or "").strip().lower()
    if not email:
        raise ValidationError("البريد الإلكتروني مطلوب.")
    if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
        raise ValidationError("هذا البريد مسجّل مسبقًا — جرّب تسجيل الدخول.")

    user = User(username=email, email=email, full_name=full_name)
    user.set_password(password)
    user.save()

    role = Role.objects.filter(code=SELF_REGISTER_ROLE).first()
    if role is not None:
        UserRole.objects.create(user=user, role=role, assigned_by=None)

    log_action(
        action="user_registered",
        entity_type="user",
        entity_id=user.pk,
        diff={"email": email, "full_name": full_name, "role": SELF_REGISTER_ROLE},
        request=request,
        actor=user,
    )
    return user


@transaction.atomic
def update_user(
    *,
    actor,
    target,
    full_name: str | None = None,
    job_title: str | None = None,
    is_active: bool | None = None,
    is_demo: bool | None = None,
    role_codes: list[str] | None = None,
    request=None,
):
    """Update profile/status/roles. Object-level rule: no self-service role edits."""
    if not has_perm(actor, "users.manage"):
        raise PermissionDenied("تعديل المستخدمين يتطلب صلاحية users.manage")
    if settings.DEPLOYMENT_ENV == "production" and (
        target.is_demo or is_demo is True
    ):
        raise ValidationError("لا يمكن إنشاء حسابات تدريبية أو تحويلها في الإنتاج.")
    if target.pk == actor.pk:
        raise PermissionDenied(
            "لا يمكن لحسابك تعديل أدوارك أو حالتك بنفسك (قاعدة Object-Level: منع قفل الذات)."
        )

    before: dict = {}
    after: dict = {}

    for field, value in (
        ("full_name", full_name),
        ("job_title", job_title),
        ("is_active", is_active),
        ("is_demo", is_demo),
    ):
        if value is not None and getattr(target, field) != value:
            before[field] = getattr(target, field)
            after[field] = value
            setattr(target, field, value)

    if before:
        target.save()
        log_action(
            action="user_updated",
            entity_type="user",
            entity_id=target.pk,
            diff={"before": before, "after": after},
            request=request,
            actor=actor,
        )

    if role_codes is not None:
        wanted = set(role_codes)
        current = set(_role_codes(target))
        if wanted != current:
            UserRole.objects.filter(user=target).delete()
            roles = Role.objects.filter(code__in=wanted)
            UserRole.objects.bulk_create(
                [UserRole(user=target, role=r, assigned_by=actor) for r in roles]
            )
            # log AFTER the change is applied (audit reflects reality)
            log_action(
                action="roles_changed",
                entity_type="user",
                entity_id=target.pk,
                diff={
                    "before": sorted(current),
                    "after": sorted(wanted),
                },
                request=request,
                actor=actor,
            )
    return target
