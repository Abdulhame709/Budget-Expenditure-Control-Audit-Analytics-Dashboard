from django.shortcuts import render

from apps.accounts.permissions import require_permission
from apps.governance.models import AuditLog


@require_permission("audittrail.view")
def audit_trail(request):
    """Recent sensitive operations — page itself is gated via URL registry too."""
    logs = AuditLog.objects.all()
    action = request.GET.get("action", "").strip()
    if action:
        logs = logs.filter(action=action)
    entity_type = request.GET.get("entity_type", "").strip()
    if entity_type:
        logs = logs.filter(entity_type=entity_type)
    actor = request.GET.get("actor", "").strip()
    if actor:
        logs = logs.filter(actor_label=actor)
    return render(request, "governance/audit_trail.html", {
        "logs": logs[:200],
        "sel": {"action": action, "entity_type": entity_type, "actor": actor},
        "action_choices": AuditLog.ACTION_CHOICES,
        "known_entity_types": sorted(
            AuditLog.objects.values_list("entity_type", flat=True).distinct()),
        "known_actors": sorted(
            AuditLog.objects.values_list("actor_label", flat=True)
            .exclude(actor_label="").distinct()),
    })


# ============================================================ PHASE 12
from django.contrib import messages  # noqa: E402
from django.db.models import Q  # noqa: E402
from django.http import (  # noqa: E402
    FileResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import get_object_or_404, redirect  # noqa: E402

from apps.accounts.permissions import require_permission  # noqa: E402
from apps.governance.models import Attachment  # noqa: E402
from apps.governance.services import log_action  # noqa: E402

# حل الكيانات المرتبطة — لعرض الرابط الوصفي والتحقق من وجود الهدف
_ATTACHMENT_TARGETS = {
    "expense": ("expenses:detail", "مصروف"),
    "procurement": ("procurement:detail", "مشتريات"),
    "audit_exception": ("audit:exception_detail", "استثناء رقابي"),
    "audit_finding": ("audit:finding_detail", "نتيجة رقابية"),
}


def attachment_entity_exists(entity_type: str, entity_id) -> bool:
    from django.apps import apps as django_apps

    model_map = {
        "expense": "expenses.Expense",
        "procurement": "procurement.Procurement",
        "audit_exception": "audit_register.AuditException",
        "audit_finding": "audit_register.AuditFinding",
    }
    if entity_type not in model_map:
        return False
    model = django_apps.get_model(model_map[entity_type])
    return model.objects.filter(pk=entity_id).exists()


def attachment_entity_link(entity_type: str, entity_id) -> tuple[str, str]:
    """(label, url) للرابط الوصفي — يُستخدم في قوالب المرفقات."""
    from django.urls import reverse

    route, label = _ATTACHMENT_TARGETS.get(entity_type, ("home", "كيان"))
    try:
        return (f"{label} #{entity_id}", reverse(route, args=[entity_id]))
    except Exception:
        return (f"{label} #{entity_id}", reverse("home"))


@require_permission("attachments.manage")
def attachment_upload(request):
    if request.method != "POST":
        return HttpResponseBadRequest("رفع المرفقات يتطلب POST.")
    entity_type = request.POST.get("entity_type", "")
    entity_id = request.POST.get("entity_id", "")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "/")
    if entity_type not in _ATTACHMENT_TARGETS or not entity_id:
        messages.error(request, "كيان غير صالح للربط.")
        return redirect(next_url)
    if not attachment_entity_exists(entity_type, entity_id):
        messages.error(request, "الكيان المطلوب غير موجود.")
        return redirect(next_url)
    upload = request.FILES.get("file")
    if upload is None:
        messages.error(request, "اختر ملفًا أولًا.")
        return redirect(next_url)
    if upload.size > 10 * 1024 * 1024:
        messages.error(request, "حجم الملف يتجاوز 10MB.")
        return redirect(next_url)
    att = Attachment.objects.create(
        file=upload,
        title=request.POST.get("title", "").strip(),
        entity_type=entity_type,
        entity_id=str(entity_id),
        uploaded_by=request.user,
        size=upload.size,
        content_type=upload.content_type or "",
    )
    log_action(
        action="attachment_uploaded",
        entity_type="attachment",
        entity_id=att.pk,
        diff={
            "title": att.title,
            "file": att.file.name,
            "size": att.size,
            "content_type": att.content_type,
            "linked": {"type": entity_type, "id": str(entity_id)},
        },
        request=request,
    )
    messages.success(request, f"رُفع المرفق «{att.file.name}» ورُبط بالـ{label_for(entity_type)}.")
    return redirect(next_url)


def label_for(entity_type: str) -> str:
    return _ATTACHMENT_TARGETS.get(entity_type, ("", "كيان"))[1]


def _attachment_response(att: Attachment, as_download: bool, request):
    disposition = "attachment" if as_download else "inline"
    response = FileResponse(att.file.open("rb"), as_attachment=as_download,
                            content_type=att.content_type or None)
    filename = att.file.name.rsplit("/", 1)[-1]
    response["Content-Disposition"] = (
        f'{disposition}; filename="{filename}"')
    log_action(
        action=("attachment_downloaded" if as_download
                else "attachment_viewed"),
        entity_type="attachment",
        entity_id=att.pk,
        diff={"file": att.file.name,
              "linked": {"type": att.entity_type, "id": att.entity_id}},
        request=request,
    )
    return response


@require_permission("attachments.view")
def attachment_view(request, pk):
    att = get_object_or_404(Attachment, pk=pk)
    return _attachment_response(att, as_download=False, request=request)


@require_permission("attachments.view")
def attachment_download(request, pk):
    att = get_object_or_404(Attachment, pk=pk)
    return _attachment_response(att, as_download=True, request=request)
