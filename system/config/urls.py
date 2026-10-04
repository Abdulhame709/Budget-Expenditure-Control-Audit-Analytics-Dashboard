"""Root URL configuration — PHASE 3: auth + accounts + audit trail."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config import views

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("health/live/", views.health_live, name="health_live"),
    path("health/ready/", views.health_ready, name="health_ready"),
    path("", views.home, name="home"),
    path("manus-routes.json", views.route_manifest, name="route_manifest"),
    path("dashboard/", include("apps.analytics.urls")),
    path("reports/", include("apps.reports.urls")),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("audit-trail/", include("apps.governance.urls")),
    path("reference/", include("apps.reference.urls")),
    path("budget/", include("apps.budget.urls")),
    path("expenses/", include("apps.expenses.urls")),
    path("procurement/", include("apps.procurement.urls")),
    path("imports/", include("apps.imports.urls")),
    path("audit/", include("apps.audit_register.urls")),
]

handler403 = "config.views.permission_denied"
handler404 = "config.views.page_not_found"
handler500 = "config.views.server_error"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
