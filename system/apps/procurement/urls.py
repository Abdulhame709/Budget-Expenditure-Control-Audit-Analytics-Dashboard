"""PHASE 7 URLs — procurement records, quotations, attachment."""
from django.urls import path

from . import views

app_name = "procurement"

urlpatterns = [
    path("", views.procurement_list, name="list"),
    path("new/", views.procurement_create, name="create"),
    path("<int:pk>/", views.procurement_detail, name="detail"),
    path("<int:pk>/edit/", views.procurement_edit, name="edit"),
    path("<int:pk>/delete/", views.procurement_delete, name="delete"),
    path("<int:pk>/attachment/", views.procurement_attachment, name="attachment"),
    path("<int:pk>/quotes/new/", views.quote_create, name="quote_create"),
    path("quotes/<int:pk>/edit/", views.quote_edit, name="quote_edit"),
    path("quotes/<int:pk>/delete/", views.quote_delete, name="quote_delete"),
]
