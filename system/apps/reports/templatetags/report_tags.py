"""PHASE 12 — فلاتر قوالب التقارير."""
from django import template

register = template.Library()


@register.filter
def cell(row, key):
    """استخراج خلية ديناميكية: {{ row|cell:c.key }}"""
    if not isinstance(row, dict):
        return None
    return row.get(key)


_FILTER_CHIP_LABELS = {
    "period": ("Period", "الفترة"),
    "department": ("Department", "الإدارة"),
    "account": ("Account", "الحساب"),
    "category": ("Category", "التصنيف"),
    "risk": ("Risk", "الخطر"),
    "test": ("Test", "الاختبار"),
}


@register.simple_tag(takes_context=True)
def filterchip(context, key):
    """اسم الفلتر بحسب اللغة المختارة."""
    lang = (context.get("LANGUAGE_CODE") or "ar")
    en, ar = _FILTER_CHIP_LABELS.get(key, (key, key))
    return en if lang == "en" else ar
