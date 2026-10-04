"""Project-level views: safe landing page, health probes and error pages."""
import hmac
import json
import os
from pathlib import Path

import django
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.db import DatabaseError, connection
from django.http import HttpResponseNotFound, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


def _db_status() -> tuple[bool, str, str]:
    """Development-only DB diagnostics; never expose details in public probes."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, connection.vendor, connection.settings_dict.get("NAME", "")
    except DatabaseError as exc:
        return False, connection.vendor, str(exc)[:120]


@require_GET
def health_live(request):
    """Public liveness probe, independent of DB and deployment configuration."""
    return JsonResponse({"status": "ok"})


@require_GET
def health_ready(request):
    """Readiness probe; hidden unless a trusted monitor supplies its secret token."""
    expected = settings.READINESS_CHECK_TOKEN
    supplied = request.headers.get("X-Readiness-Token", "")
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        return HttpResponseNotFound()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    response = JsonResponse({"status": "ready"})
    response["Cache-Control"] = "no-store"
    return response


def home(request):
    """Application landing page; secure environments require authentication."""
    if (
        settings.DEPLOYMENT_ENV in {"staging", "production"}
        and not request.user.is_authenticated
    ):
        return redirect_to_login(request.get_full_path())

    show_environment_details = settings.DEPLOYMENT_ENV == "development"
    db_ok, db_vendor, db_name = _db_status()
    from apps.budget.models import BudgetLine
    from apps.expenses.models import Expense
    from apps.procurement.models import Procurement
    from apps.reference.models import Account, Department, Supplier

    context = {
        "deployment_env": settings.DEPLOYMENT_ENV,
        "show_environment_details": show_environment_details,
        "django_version": django.get_version() if show_environment_details else "",
        "db_ok": db_ok,
        "db_vendor": db_vendor,
        "db_name": db_name,
        "db_host": connection.settings_dict.get("HOST", "localhost"),
        "db_port": connection.settings_dict.get("PORT", "5432"),
        "database_platform_label": settings.DATABASE_PLATFORM_LABEL,
        "storage_status": (
            "connected" if settings.IMPORT_FILE_STORAGE_CONFIGURED
            else "unconfigured"
        ),
        "supabase_project_ref": settings.SUPABASE_PROJECT_REF,
        "record_counts": {
            "departments": Department.objects.count(),
            "accounts": Account.objects.count(),
            "suppliers": Supplier.objects.count(),
            "budget_lines": BudgetLine.objects.count(),
            "expenses": Expense.objects.count(),
            "procurements": Procurement.objects.count(),
        },
        "settings_module": "",
        "apps_count": 0,
        "is_debug": settings.DEBUG,
    }
    if show_environment_details:
        context.update({
            "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE", ""),
            "apps_count": len(settings.INSTALLED_APPS),
        })
    return render(request, "home.html", context)


@require_GET
def route_manifest(request):
    if (
        settings.DEPLOYMENT_ENV in {"staging", "production"}
        and not request.user.is_authenticated
    ):
        return redirect_to_login(request.get_full_path())
    manifest_path = Path(__file__).resolve().parents[1] / "route_manifest.json"
    return JsonResponse(json.loads(manifest_path.read_text(encoding="utf-8")))


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)
