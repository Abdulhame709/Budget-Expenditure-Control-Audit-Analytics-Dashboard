"""PHASE 5 URLs — budget / versions / lines / summary."""
from django.urls import path

from . import views

app_name = "budget"

urlpatterns = [
    path("", views.budget_list, name="budget_list"),
    path("new/", views.budget_create, name="budget_create"),
    path("<int:pk>/", views.budget_detail, name="budget_detail"),
    path("<int:pk>/edit/", views.budget_edit, name="budget_edit"),
    path("<int:pk>/delete/", views.budget_delete, name="budget_delete"),
    # versions
    path("versions/<int:pk>/", views.version_detail, name="version_detail"),
    path("versions/<int:pk>/edit/", views.version_edit, name="version_edit"),
    path("versions/<int:pk>/approve/", views.version_approve,
         name="version_approve"),
    path("versions/<int:pk>/unapprove/", views.version_unapprove,
         name="version_unapprove"),
    path("versions/<int:pk>/summary/", views.version_summary,
         name="version_summary"),
    path("budgets/<int:budget_pk>/new-revision/", views.version_new_revision,
         name="version_new_revision"),
    # lines
    path("versions/<int:version_pk>/lines/new/", views.line_create,
         name="line_create"),
    path("lines/<int:pk>/edit/", views.line_edit, name="line_edit"),
    path("lines/<int:pk>/delete/", views.line_delete, name="line_delete"),
]
