"""Template helpers for import-sheet rendering (Arabic-first display)."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()


def _to_decimal(value):
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


@register.filter
def isnum(value):
    """True when the cell holds a numeric amount."""
    return _to_decimal(value) is not None


@register.filter
def numfmt(value):
    """Thousands separators, rounded to a whole number (no fractions)."""
    number = _to_decimal(value)
    if number is None:
        return "" if value is None else value
    rounded = number.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,}"
