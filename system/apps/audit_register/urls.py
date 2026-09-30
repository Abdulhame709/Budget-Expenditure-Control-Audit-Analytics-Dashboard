"""PHASE 9 — audit test engine URLs (app_name = audit)."""
from django.urls import path

from apps.audit_register import views

app_name = "audit"

urlpatterns = [
    path("", views.cycle_hub, name="cycle_hub"),
    path("tests/", views.tests_list, name="tests_list"),
    path("tests/new/", views.test_create, name="test_create"),
    path("tests/<int:pk>/edit/", views.test_edit, name="test_edit"),
    path("tests/<int:pk>/toggle/", views.test_toggle, name="test_toggle"),
    path("runs/", views.runs_list, name="runs_list"),
    path("runs/start/", views.run_start, name="run_start"),
    path("runs/<int:pk>/", views.run_detail, name="run_detail"),
    path("exceptions/", views.exceptions_list, name="exceptions_list"),
    path("exceptions/<int:pk>/", views.exception_detail,
         name="exception_detail"),
    path("exceptions/<int:pk>/update/", views.exception_update,
         name="exception_update"),
    path("exceptions/<int:pk>/evidence/", views.exception_evidence_upload,
         name="evidence_upload"),
    path("exceptions/<int:pk>/evidence/view/",
         views.exception_evidence_view, name="evidence_view"),
    path("findings/", views.findings_list, name="findings_list"),
    path("findings/new/", views.finding_create, name="finding_create"),
    path("findings/<int:pk>/", views.finding_detail, name="finding_detail"),
    path("findings/<int:pk>/edit/", views.finding_edit, name="finding_edit"),
]
