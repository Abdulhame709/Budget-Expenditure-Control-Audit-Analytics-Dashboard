from django.urls import path

from apps.governance import views

app_name = "governance"

urlpatterns = [
    path("", views.audit_trail, name="audit_trail"),
    path("cloud-sync/", views.cloud_sync, name="cloud_sync"),
    # PHASE 12 — attachments
    path("attachments/upload/", views.attachment_upload,
         name="attachment_upload"),
    path("attachments/<int:pk>/view/", views.attachment_view,
         name="attachment_view"),
    path("attachments/<int:pk>/download/", views.attachment_download,
         name="attachment_download"),
]
