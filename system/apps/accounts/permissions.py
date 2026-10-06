"""RBAC permission catalog, URL registry, helpers and decorators (PHASE 3).

Single source of truth:
- PERMISSIONS      : every permission code in the system
- ROLES            : the four approved roles + the codes they grant
- URL_PERMISSIONS  : page-level gate — map URL view_name → required permission

Access rules:
- page-level  → URL_PERMISSIONS enforced by AccessControlMiddleware (direct URLs included)
- action-level → @require_permission decorator on mutating views
- object-level → services (e.g. users cannot change their own roles)
"""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

# ---------------------------------------------------------------- catalog
# code: (module, label_ar)
PERMISSIONS: dict[str, tuple[str, str]] = {
    # system administration
    "users.view": ("users", "عرض المستخدمين"),
    "users.manage": ("users", "إدارة المستخدمين"),
    "roles.view": ("roles", "عرض الأدوار"),
    "roles.manage": ("roles", "إدارة الأدوار والصلاحيات"),
    "settings.manage": ("settings", "إعدادات النظام"),
    "audittrail.view": ("audittrail", "عرض سجل التدقيق"),
    # reference data
    "reference.view": ("reference", "عرض البيانات المرجعية"),
    "reference.edit": ("reference", "تعديل البيانات المرجعية"),
    # periods (PHASE 4 — closed-period posting override)
    "periods.post_closed": ("periods", "التسجيل في فترة مغلقة (تجاوز مُصرَّح)"),
    # financial / operational
    "dashboard.view": ("dashboard", "عرض لوحة المؤشرات"),
    "budget.view": ("budget", "عرض الموازنة"),
    "budget.edit": ("budget", "تعديل الموازنة"),
    "expenses.view": ("expenses", "عرض المصروفات"),
    "expenses.edit": ("expenses", "تعديل المصروفات"),
    "procurement.view": ("procurement", "عرض المشتريات"),
    "procurement.edit": ("procurement", "تعديل المشتريات"),
    "imports.view": ("imports", "عرض الاستيراد"),
    "imports.run": ("imports", "تنفيذ عمليات الاستيراد"),
    # audit
    "audit.view": ("audit", "عرض الاختبارات الرقابية"),
    "audit.run": ("audit", "تشغيل الاختبارات"),
    "audit.rules.manage": ("audit", "إدارة قواعد الاختبارات"),
    "exceptions.view": ("exceptions", "عرض الاستثناءات"),
    "exceptions.manage": ("exceptions", "معالجة الاستثناءات"),
    "risk.view": ("risk", "عرض تقييم المخاطر"),
    "findings.view": ("findings", "عرض النتائج والملاحظات"),
    "findings.manage": ("findings", "إعداد النتائج والتوصيات"),
    "reports.view": ("reports", "عرض التقارير"),
    "reports.generate": ("reports", "إنشاء/تصدير التقارير"),
    "attachments.view": ("attachments", "عرض المرفقات"),
    "attachments.manage": ("attachments", "إرفاق الوثائق والأدلة"),
}

ALL_CODES = frozenset(PERMISSIONS)

# ---------------------------------------------------------------- roles (approved matrix)
_AUDIT_CORE = {
    "dashboard.view", "reference.view", "budget.view", "expenses.view",
    "procurement.view", "attachments.view", "attachments.manage",
    "audit.view", "audit.run", "audit.rules.manage",
    "exceptions.view", "exceptions.manage", "risk.view",
    "findings.view", "findings.manage",
    "reports.view", "reports.generate", "audittrail.view",
}
_FINANCE_CORE = {
    "dashboard.view", "reference.view",
    "budget.view", "budget.edit",
    "expenses.view", "expenses.edit",
    "procurement.view", "procurement.edit",
    "imports.view", "imports.run",
    "reports.view", "reports.generate",
}
_MANAGEMENT_CORE = {
    "dashboard.view", "reports.view", "findings.view", "risk.view",
    "exceptions.view",
}
_PROJECT_VIEWER_CORE = {
    "dashboard.view", "reference.view", "budget.view", "expenses.view",
    "procurement.view", "imports.view", "audit.view", "exceptions.view",
    "risk.view", "findings.view", "reports.view", "attachments.view",
}

ROLES: dict[str, dict] = {
    "admin": {
        "name_ar": "مدير النظام",
        "name_en": "Administrator",
        "description": "إدارة كاملة: مستخدمون، أدوار، إعدادات، وكل الوحدات.",
        "permissions": set(ALL_CODES),
    },
    "auditor": {
        "name_ar": "مدقق داخلي",
        "name_en": "Auditor / Internal Auditor",
        "description": "الاختبارات، الاستثناءات، المخاطر، النتائج، التقارير، الأدلة + قراءة تشغيلية.",
        "permissions": set(_AUDIT_CORE),
    },
    "finance": {
        "name_ar": "موظف مالية",
        "name_en": "Finance User",
        "description": "الموازنة والمصروفات والمشتريات والاستيراد + تقارير مالية.",
        "permissions": set(_FINANCE_CORE),
    },
    "management": {
        "name_ar": "الإدارة / مشاهدة",
        "name_en": "Management / Viewer",
        "description": "قراءة فقط: لوحة، تقارير، نتائج، مخاطر، استثناءات — بلا أي تعديل.",
        "permissions": set(_MANAGEMENT_CORE),
    },
    "viewer": {
        "name_ar": "مستعرض المشروع",
        "name_en": "Project Viewer",
        "description": "قراءة الوحدات التشغيلية والتقارير والمرفقات دون تعديل أو إدارة.",
        "permissions": set(_PROJECT_VIEWER_CORE),
    },
}

# ---------------------------------------------------------------- page-level gate
# Any URL NOT listed here is public-by-policy (home, login, static, django admin).
URL_PERMISSIONS: dict[str, str] = {
    "accounts:users_list": "users.manage",
    "accounts:user_create": "users.manage",
    "accounts:user_detail": "users.manage",
    "accounts:user_password_reset": "users.manage",
    "accounts:roles_list": "roles.manage",
    "governance:audit_trail": "audittrail.view",
}

# PHASE 4 — every reference module page (direct URL included)
for _slug in ("currency", "fiscal_year", "period", "department", "employee", "account",
              "expense_category", "supplier"):
    URL_PERMISSIONS[f"reference:{_slug}_list"] = "reference.view"
    URL_PERMISSIONS[f"reference:{_slug}_detail"] = "reference.view"
    URL_PERMISSIONS[f"reference:{_slug}_create"] = "reference.edit"
    URL_PERMISSIONS[f"reference:{_slug}_edit"] = "reference.edit"
    URL_PERMISSIONS[f"reference:{_slug}_delete"] = "reference.edit"
URL_PERMISSIONS["reference:period_set_status"] = "reference.edit"
URL_PERMISSIONS["reference:organization_settings"] = "settings.manage"
URL_PERMISSIONS["reference:analytical_accounts"] = "reference.view"
del _slug

# PHASE 5 — budget pages
URL_PERMISSIONS.update({
    "budget:budget_list": "budget.view",
    "budget:budget_detail": "budget.view",
    "budget:version_detail": "budget.view",
    "budget:version_summary": "budget.view",
    "budget:version_grid_update": "budget.edit",
    "budget:budget_create": "budget.edit",
    "budget:budget_edit": "budget.edit",
    "budget:budget_delete": "budget.edit",
    "budget:version_edit": "budget.edit",
    "budget:version_approve": "budget.edit",
    "budget:version_unapprove": "budget.edit",
    "budget:version_new_revision": "budget.edit",
    "budget:line_create": "budget.edit",
    "budget:line_edit": "budget.edit",
    "budget:line_delete": "budget.edit",
    "budget:plan_list": "budget.view",
    "budget:plan_detail": "budget.view",
    "budget:plan_monthly_output": "budget.view",
    "budget:plan_summary_output": "budget.view",
    "budget:plan_analytical_accounts": "budget.view",
    "budget:plan_department_employees": "budget.view",
    "budget:plan_create": "budget.edit",
    "budget:plan_edit": "budget.edit",
    "budget:plan_delete": "budget.edit",
    "budget:plan_section_create": "budget.edit",
    "budget:plan_section_edit": "budget.edit",
    "budget:plan_section_delete": "budget.edit",
    "budget:plan_line_create": "budget.edit",
    "budget:plan_line_edit": "budget.edit",
    "budget:plan_line_delete": "budget.edit",
    "budget:plan_line_copy": "budget.edit",
    "budget:template_list": "budget.view",
    "budget:template_detail": "budget.view",
    "budget:template_sheet": "budget.view",
    "budget:template_import": "budget.edit",
    "budget:template_edit": "budget.edit",
    "budget:template_delete": "budget.edit",
})

# PHASE 6 — actual expenses
URL_PERMISSIONS.update({
    "expenses:list": "expenses.view",
    "expenses:detail": "expenses.view",
    "expenses:attachment": "expenses.view",
    "expenses:export": "expenses.view",
    "expenses:create": "expenses.edit",
    "expenses:edit": "expenses.edit",
})

# PHASE 7 — procurement
URL_PERMISSIONS.update({
    "procurement:list": "procurement.view",
    "procurement:detail": "procurement.view",
    "procurement:attachment": "procurement.view",
    "procurement:create": "procurement.edit",
    "procurement:edit": "procurement.edit",
    "procurement:delete": "procurement.edit",
    "procurement:quote_create": "procurement.edit",
    "procurement:quote_edit": "procurement.edit",
    "procurement:quote_delete": "procurement.edit",
})

# PHASE 8 — import pipeline (existing catalog codes; catalog stays 30)
URL_PERMISSIONS.update({
    "imports:list": "imports.view",
    "imports:detail": "imports.view",
    "imports:file": "imports.view",
    "imports:template": "imports.view",
    "imports:new": "imports.run",
    "imports:validate": "imports.run",
    "imports:confirm": "imports.run",
    "imports:cancel": "imports.run",
})

# PHASE 9 — audit test engine (existing catalog codes; catalog stays 30)
URL_PERMISSIONS.update({
    "audit:tests_list": "audit.view",
    "audit:runs_list": "audit.view",
    "audit:run_detail": "audit.view",
    "audit:test_create": "audit.rules.manage",
    "audit:test_edit": "audit.rules.manage",
    "audit:test_toggle": "audit.rules.manage",
    "audit:run_start": "audit.run",
    "audit:exceptions_list": "exceptions.view",
    "audit:exception_detail": "exceptions.view",
    "audit:evidence_view": "exceptions.view",
    "audit:exception_update": "exceptions.manage",
    "audit:evidence_upload": "exceptions.manage",
    "audit:cycle_hub": "audit.view",
    "audit:findings_list": "findings.view",
    "audit:finding_detail": "findings.view",
    "audit:finding_create": "findings.manage",
    "audit:finding_edit": "findings.manage",
})

# PHASE 11 — interactive dashboard (reuses dashboard.view; catalog stays 30)
URL_PERMISSIONS.update({
    "dashboard:index": "dashboard.view",
})

# PHASE 12 — reporting system + attachments (existing codes; catalog stays 30)
URL_PERMISSIONS.update({
    "reports:list": "reports.view",
    "reports:detail": "reports.view",
    "reports:export": "reports.generate",
    "governance:attachment_upload": "attachments.manage",
    "governance:attachment_view": "attachments.view",
    "governance:attachment_download": "attachments.view",
    "governance:cloud_sync": "settings.manage",
})

# ---------------------------------------------------------------- helpers
def user_permission_codes(user) -> frozenset:
    """Effective permission codes for a user (superuser ⇒ everything)."""
    if not getattr(user, "is_authenticated", False):
        return frozenset()
    if user.is_superuser:
        return ALL_CODES
    from apps.accounts.models import UserRole  # local import: avoid app-load cycle

    rows = UserRole.objects.filter(user=user).values_list(
        "role__role_permissions__permission__code", flat=True
    )
    return frozenset(rows)


def has_perm(user, code: str) -> bool:
    """Single authorization predicate used by pages, actions and templates."""
    if code not in ALL_CODES:
        raise ValueError(f"Unknown permission code: {code}")
    return code in user_permission_codes(user)


# ---------------------------------------------------------------- decorators
def require_permission(code: str):
    """Action-level (and defense-in-depth page-level) permission gate."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not has_perm(request.user, code):
                raise PermissionDenied(
                    f"ليست لديك صلاحية: {code} — {PERMISSIONS.get(code, ('', ''))[1]}"
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
