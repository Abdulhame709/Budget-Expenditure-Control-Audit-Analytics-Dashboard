"""PHASE 4 URLs — six modules × (list / create / detail / edit / delete)
+ period open/close action."""
from django.urls import path

from . import views

app_name = "reference"

urlpatterns = []
for _slug, _cfg in views.REFERENCE_MODULES.items():
    _base = _cfg["path"]
    urlpatterns += [
        path(f"{_base}/", views.module_list, {"slug": _slug},
             name=f"{_slug}_list"),
        path(f"{_base}/new/", views.module_create, {"slug": _slug},
             name=f"{_slug}_create"),
        path(f"{_base}/<int:pk>/", views.module_detail, {"slug": _slug},
             name=f"{_slug}_detail"),
        path(f"{_base}/<int:pk>/edit/", views.module_edit, {"slug": _slug},
             name=f"{_slug}_edit"),
        path(f"{_base}/<int:pk>/delete/", views.module_delete, {"slug": _slug},
             name=f"{_slug}_delete"),
    ]

urlpatterns += [
    path("organization-settings/", views.organization_settings,
         name="organization_settings"),
    path("periods/<int:pk>/set-status/", views.period_set_status,
         name="period_set_status"),
]
