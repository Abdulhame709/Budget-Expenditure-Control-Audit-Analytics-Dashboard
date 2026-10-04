"""Neutralize spreadsheet formula injection in CSV and XLSX cell exports."""
from decimal import Decimal, InvalidOperation
import re

_FORMULA_PREFIX = re.compile(r"^[\s\x00-\x20\x7f-\x9f\ufeff\u200b]*[=+\-@]")


def safe_spreadsheet_value(value):
    """Prefix dangerous text with an apostrophe while preserving real numbers."""
    if value is None:
        return ""
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return value

    text = str(value)
    if not _FORMULA_PREFIX.match(text):
        return text

    # Negative numeric text is ordinary data (not a spreadsheet expression).
    try:
        Decimal(text.strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return "'" + text
    return text
