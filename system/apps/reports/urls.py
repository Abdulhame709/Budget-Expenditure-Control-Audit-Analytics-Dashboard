"""PHASE 12 — مسارات نظام التقارير."""
from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("export/<slug:slug>/<str:fmt>/", views.report_export,
         name="export"),
    path("<slug:slug>/", views.report_detail, name="detail"),
]
