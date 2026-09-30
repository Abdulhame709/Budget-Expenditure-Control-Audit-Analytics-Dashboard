"""PHASE 8 — import pipeline URLs (app_name = imports)."""
from django.urls import path

from apps.imports import views

app_name = "imports"

urlpatterns = [
    path("", views.import_list, name="list"),
    path("new/", views.import_new, name="new"),
    path("<int:pk>/", views.import_detail, name="detail"),
    path("<int:pk>/validate/", views.import_validate, name="validate"),
    path("<int:pk>/confirm/", views.import_confirm, name="confirm"),
    path("<int:pk>/cancel/", views.import_cancel, name="cancel"),
    path("<int:pk>/file/", views.import_file, name="file"),
]
