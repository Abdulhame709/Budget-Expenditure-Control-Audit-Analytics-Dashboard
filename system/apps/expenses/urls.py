"""PHASE 6 URLs — actual expenses."""
from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list, name="list"),
    path("new/", views.expense_create, name="create"),
    path("export/", views.expense_export, name="export"),
    path("<int:pk>/", views.expense_detail, name="detail"),
    path("<int:pk>/edit/", views.expense_edit, name="edit"),
    path("<int:pk>/attachment/", views.expense_attachment, name="attachment"),
]
