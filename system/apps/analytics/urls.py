"""PHASE 11 — مسارات لوحة المؤشرات."""
from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="index"),
]
