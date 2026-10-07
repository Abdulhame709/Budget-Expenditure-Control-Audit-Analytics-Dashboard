"""PHASE 5 URLs — budget / versions / lines / summary."""
from django.urls import path

from . import views

app_name = "budget"

urlpatterns = [
    path("plans/", views.plan_list, name="plan_list"),
    path("plans/new/", views.plan_create, name="plan_create"),
    path("plans/<int:pk>/", views.plan_detail, name="plan_detail"),
    path("plans/<int:pk>/edit/", views.plan_edit, name="plan_edit"),
    path("plans/<int:pk>/delete/", views.plan_delete, name="plan_delete"),
    path("plans/<int:pk>/monthly/", views.plan_monthly_output, name="plan_monthly_output"),
    path("plans/<int:pk>/summary/", views.plan_summary_output, name="plan_summary_output"),
    path("plans/<int:plan_pk>/sections/new/", views.plan_section_create, name="plan_section_create"),
    path("plan-sections/<int:pk>/edit/", views.plan_section_edit, name="plan_section_edit"),
    path("plan-sections/<int:pk>/delete/", views.plan_section_delete, name="plan_section_delete"),
    path("plan-sections/<int:pk>/bulk-lines/", views.plan_section_bulk_lines, name="plan_section_bulk_lines"),
    path("plan-sections/<int:pk>/import-template/", views.plan_section_import_template, name="plan_section_import_template"),
    path("plan-sections/<int:section_pk>/lines/new/", views.plan_line_create, name="plan_line_create"),
    path("plan-lines/<int:pk>/edit/", views.plan_line_edit, name="plan_line_edit"),
    path("plan-lines/<int:pk>/delete/", views.plan_line_delete, name="plan_line_delete"),
    path("plan-lines/<int:pk>/copy/", views.plan_line_copy, name="plan_line_copy"),
    path("plan-lines/<int:pk>/move/<str:direction>/", views.plan_line_move, name="plan_line_move"),
    path("plan-lines/<int:pk>/toggle-included/", views.plan_line_toggle_included, name="plan_line_toggle_included"),
    path("plans/api/analytical-accounts/", views.plan_analytical_accounts, name="plan_analytical_accounts"),
    path("plans/api/employees/", views.plan_department_employees, name="plan_department_employees"),
    path("templates/", views.template_list, name="template_list"),
    path("templates/import/", views.template_import, name="template_import"),
    path("templates/<int:pk>/", views.template_detail, name="template_detail"),
    path("templates/<int:pk>/edit/", views.template_edit, name="template_edit"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
    path("template-sheets/<int:pk>/", views.template_sheet, name="template_sheet"),
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
    path("versions/<int:pk>/grid-update/", views.version_grid_update,
         name="version_grid_update"),
    path("budgets/<int:budget_pk>/new-revision/", views.version_new_revision,
         name="version_new_revision"),
    # lines
    path("versions/<int:version_pk>/lines/new/", views.line_create,
         name="line_create"),
    path("lines/<int:pk>/edit/", views.line_edit, name="line_edit"),
    path("lines/<int:pk>/delete/", views.line_delete, name="line_delete"),
]
