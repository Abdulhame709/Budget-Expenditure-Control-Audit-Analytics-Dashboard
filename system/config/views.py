"""Project-level views: home (system status) + error pages."""
import django
from django.db import connection
from django.db.utils import OperationalError
from django.shortcuts import render


def _db_status() -> tuple[bool, str, str]:
    """Real database probe — the home page never shows invented numbers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, connection.vendor, connection.settings_dict.get("NAME", "")
    except OperationalError as exc:
        return False, connection.vendor, str(exc)[:120]


def home(request):
    db_ok, db_vendor, db_name = _db_status()
    return render(
        request,
        "home.html",
        {
            "django_version": django.get_version(),
            "db_ok": db_ok,
            "db_vendor": db_vendor,
            "db_name": db_name,
            "settings_module": __import__("os").environ.get(
                "DJANGO_SETTINGS_MODULE", ""
            ),
            "apps_count": len(__import__("django.conf", fromlist=["settings"]).settings.INSTALLED_APPS),
            "debug": request.GET.get("debug") is not None or None,
            "is_debug": __import__("django.conf", fromlist=["settings"]).settings.DEBUG,
        },
    )


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)
