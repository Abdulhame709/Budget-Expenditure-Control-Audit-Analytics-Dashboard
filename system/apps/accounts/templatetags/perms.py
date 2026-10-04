"""Template tag: permission checks in templates (same predicate as middleware)."""
from django import template

from apps.accounts.permissions import has_perm

register = template.Library()


@register.simple_tag
def perm(user, code):
    """{% perm user 'users.manage' as can_users %} → True/False."""
    return has_perm(user, code)
