"""accounts: custom user + RBAC tables (approved Phase-1 schema).

Tables: users (User) · roles · permissions · user_roles · role_permissions
Authorization model: permission codes (module.action) → roles → users.
"""
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.db import models


class User(AbstractUser):
    """System user — extended with profile fields from the approved schema."""

    full_name = models.CharField("الاسم الكامل", max_length=150, blank=True)
    job_title = models.CharField("المسمى الوظيفي", max_length=150, blank=True)
    is_demo = models.BooleanField(
        "حساب تدريبي",
        default=False,
        help_text="True لحسابات Demo/Seed المُعلَنة كتدريبية (Synthetic Training Data).",
    )

    class Meta(AbstractUser.Meta):
        verbose_name = "مستخدم"
        db_table = "users"

    def __str__(self):
        return self.get_full_name() or self.username


class Role(models.Model):
    """دور — قابل للتوسع (D-05 spirit): إضافة دور جديد لا تتطلب كودًا."""

    code = models.SlugField("الرمز", max_length=40, unique=True)
    name_ar = models.CharField("الاسم (عربي)", max_length=100)
    name_en = models.CharField("الاسم (EN)", max_length=100, blank=True)
    description = models.TextField("الوصف", blank=True)
    is_system = models.BooleanField(
        "دور نظام", default=True,
        help_text="الدور المبني في النظام؛ لا يُحذف (يمكن تعديل صلاحياته).",
    )

    class Meta:
        db_table = "roles"
        verbose_name = "دور"
        verbose_name_plural = "الأدوار"
        ordering = ["code"]

    def __str__(self):
        return f"{self.name_ar} ({self.code})"


class Permission(models.Model):
    """صلاحية بنمط module.action — المصدر الوحيد لتعريف الصلاحيات."""

    code = models.SlugField("الرمز", max_length=60, unique=True)
    module = models.SlugField("الوحدة", max_length=30, db_index=True)
    label_ar = models.CharField("الوصف (عربي)", max_length=150)
    description = models.TextField("تفاصيل", blank=True)

    class Meta:
        db_table = "permissions"
        verbose_name = "صلاحية"
        verbose_name_plural = "الصلاحيات"
        ordering = ["module", "code"]

    def __str__(self):
        return self.code


class UserRole(models.Model):
    """ربط مستخدم ↔ دور (unique)."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="role_links",
        verbose_name="المستخدم",
    )
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="memberships",
        verbose_name="الدور",
    )
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="role_assignments_made", verbose_name="مُسند بواسطة",
    )
    created_at = models.DateTimeField("تاريخ الإسناد", auto_now_add=True)

    class Meta:
        db_table = "user_roles"
        verbose_name = "إسناد دور"
        verbose_name_plural = "إسنادات الأدوار"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uq_user_role"),
        ]

    def __str__(self):
        return f"{self.user} → {self.role.code}"


class RolePermission(models.Model):
    """ربط دور ↔ صلاحية (unique)."""

    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="role_permissions",
        verbose_name="الدور",
    )
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="granted_to",
        verbose_name="الصلاحية",
    )
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="permission_grants_made", verbose_name="مُعتمد بواسطة",
    )
    created_at = models.DateTimeField("تاريخ المنح", auto_now_add=True)

    class Meta:
        db_table = "role_permissions"
        verbose_name = "صلاحية دور"
        verbose_name_plural = "صلاحيات الأدوار"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uq_role_permission"),
        ]

    def __str__(self):
        return f"{self.role.code}:{self.permission.code}"
