"""PHASE 12 — وسم قسم المرفقات (inclusion tag)."""
from django import template

from apps.governance.models import Attachment

register = template.Library()


@register.inclusion_tag("governance/_attachments.html", takes_context=True)
def attachment_section(context, entity_type: str, entity_id) -> dict:
    """يعرض المرفقات المرتبطة بكيان + نموذج الرفع (حسب الصلاحية)."""
    request = context.get("request")
    user = getattr(request, "user", None)
    can_view = can_manage = False
    if user is not None and user.is_authenticated:
        from apps.accounts.permissions import has_perm
        can_view = has_perm(user, "attachments.view")
        can_manage = has_perm(user, "attachments.manage")
    return {
        "atts": (Attachment.objects.filter(
            entity_type=entity_type, entity_id=str(entity_id))
            if can_view else Attachment.objects.none()),
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "can_view": can_view,
        "can_manage": can_manage,
        "request": request,
    }
