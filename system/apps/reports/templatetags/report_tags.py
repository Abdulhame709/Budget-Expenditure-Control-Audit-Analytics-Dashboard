"""PHASE 12 — فلاتر قوالب التقارير."""
from django import template

register = template.Library()


@register.filter
def cell(row, key):
    """استخراج خلية ديناميكية: {{ row|cell:c.key }}"""
    if not isinstance(row, dict):
        return None
    return row.get(key)
