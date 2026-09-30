"""Small template filters for the PHASE 4 generic views."""
from django import template

register = template.Library()


@register.filter
def get(mapping, key):
    """dict[key] with a default of '' (for rendering active filter values)."""
    try:
        return mapping.get(key, "") if mapping else ""
    except AttributeError:
        return ""
