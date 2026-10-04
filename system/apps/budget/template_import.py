from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.db import transaction
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from apps.reference.models import Account, Currency

from .models import (
    BudgetTemplate,
    BudgetTemplateCell,
    BudgetTemplateColumn,
    BudgetTemplateRow,
    BudgetTemplateSheet,
)


MONTH_NAMES = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4,
    "مايو": 5, "يونيو": 6, "يوليو": 7, "أغسطس": 8, "اغسطس": 8,
    "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}


def _text(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _color(value):
    if not value:
        return ""
    rgb = getattr(value, "rgb", None)
    return rgb if isinstance(rgb, str) else ""


def _style(cell) -> dict:
    return {
        "bold": bool(cell.font.bold),
        "italic": bool(cell.font.italic),
        "font_color": _color(cell.font.color),
        "fill_color": _color(cell.fill.fgColor),
        "horizontal": cell.alignment.horizontal or "",
        "vertical": cell.alignment.vertical or "",
        "wrap_text": bool(cell.alignment.wrap_text),
        "border": bool(cell.border.left.style or cell.border.right.style
                       or cell.border.top.style or cell.border.bottom.style),
    }


def _sheet_purpose(name: str, values: list[str]) -> str:
    text = " ".join([name, *values[:80]])
    if "إجمالي" in text or "اجمالي" in text:
        return BudgetTemplateSheet.PURPOSE_SUMMARY
    if any(month in text for month in MONTH_NAMES) or "شهري" in text:
        return BudgetTemplateSheet.PURPOSE_MONTHLY
    if "تفصيلي" in text or "تفصيل" in text:
        return BudgetTemplateSheet.PURPOSE_DETAIL
    return BudgetTemplateSheet.PURPOSE_SUPPORTING


def _row_type(values: list[str], bold_count: int, merged: bool) -> str:
    text = " ".join(values).strip()
    if not text:
        return BudgetTemplateRow.TYPE_NOTE
    if "الإجمالي" in text or "الاجمالي" in text or text.startswith("إجمالي"):
        return BudgetTemplateRow.TYPE_TOTAL
    if "المجموع" in text or "جملة" in text:
        return BudgetTemplateRow.TYPE_SUBTOTAL
    if merged and len(values) <= 2:
        return BudgetTemplateRow.TYPE_TITLE
    if bold_count >= max(1, len(values) // 2) and not any(char.isdigit() for char in text):
        return BudgetTemplateRow.TYPE_HEADER
    return BudgetTemplateRow.TYPE_DATA


def _column_role(title: str) -> str:
    normalized = (title or "").strip().lower()
    if "رقم الحساب" in normalized or "كود الحساب" in normalized:
        return BudgetTemplateColumn.ROLE_ACCOUNT_CODE
    if "اسم الحساب" in normalized or normalized == "الحساب":
        return BudgetTemplateColumn.ROLE_ACCOUNT_NAME
    if "إجمالي" in normalized or "اجمالي" in normalized or "سنوي" in normalized:
        return BudgetTemplateColumn.ROLE_ANNUAL
    if "ملاحظ" in normalized or "بيان" == normalized:
        return BudgetTemplateColumn.ROLE_NOTES
    for month_name, month in MONTH_NAMES.items():
        if month_name in normalized:
            return f"month_{month:02d}"
    return BudgetTemplateColumn.ROLE_GENERIC


def _account_match(values: list[str], accounts_by_code: dict, accounts_by_name: dict):
    for value in values:
        cleaned = value.strip()
        if cleaned in accounts_by_code:
            return accounts_by_code[cleaned]
    joined = " ".join(values).strip().lower()
    for name, account in accounts_by_name.items():
        if name and (joined == name or name in joined):
            return account
    return None


@transaction.atomic
def import_budget_workbook(file_or_path, *, name: str, description: str = "", user=None):
    source_reference = getattr(file_or_path, "name", None) or str(file_or_path)
    keep_vba = str(source_reference).lower().endswith(".xlsm")
    workbook = load_workbook(file_or_path, data_only=False, keep_vba=keep_vba)
    source_name = Path(source_reference).name
    base_currency = Currency.objects.filter(is_base=True).first()
    template = BudgetTemplate.objects.create(
        name=name,
        description=description,
        source_filename=source_name,
        currency=base_currency,
        workbook_metadata={
            "sheet_count": len(workbook.sheetnames),
            "sheet_names": workbook.sheetnames,
            "calculation_mode": getattr(workbook.calculation, "calcMode", None),
        },
        created_by=user,
        updated_by=user,
    )
    accounts = list(Account.objects.filter(account_type="expense", is_active=True))
    accounts_by_code = {str(account.code).strip(): account for account in accounts}
    accounts_by_name = {account.name.strip().lower(): account for account in accounts}

    for position, worksheet in enumerate(workbook.worksheets, start=1):
        merged_ranges = [str(value) for value in worksheet.merged_cells.ranges]
        non_empty_text = [
            _text(cell.value)
            for row in worksheet.iter_rows()
            for cell in row
            if cell.value not in (None, "")
        ]
        sheet = BudgetTemplateSheet.objects.create(
            template=template,
            name=worksheet.title,
            position=position,
            purpose=_sheet_purpose(worksheet.title, non_empty_text),
            state=worksheet.sheet_state,
            max_row=worksheet.max_row,
            max_column=worksheet.max_column,
            freeze_panes=_text(worksheet.freeze_panes),
            merged_ranges=merged_ranges,
            layout_metadata={
                "sheet_view": {
                    "show_grid_lines": worksheet.sheet_view.showGridLines,
                    "right_to_left": worksheet.sheet_view.rightToLeft,
                },
                "page_orientation": worksheet.page_setup.orientation,
            },
            created_by=user,
            updated_by=user,
        )

        columns = {}
        for column_index in range(1, worksheet.max_column + 1):
            column_letter = get_column_letter(column_index)
            title = ""
            for row_number in range(1, min(worksheet.max_row, 20) + 1):
                value = worksheet.cell(row_number, column_index).value
                if value not in (None, ""):
                    title = _text(value)[:255]
                    break
            dimension = worksheet.column_dimensions[column_letter]
            columns[column_index] = BudgetTemplateColumn.objects.create(
                sheet=sheet,
                column_index=column_index,
                column_letter=column_letter,
                title=title,
                role=_column_role(title),
                width=dimension.width,
                is_hidden=bool(dimension.hidden),
            )

        merged_rows = set()
        for merged_range in worksheet.merged_cells.ranges:
            merged_rows.update(range(merged_range.min_row, merged_range.max_row + 1))

        for row_number in range(1, worksheet.max_row + 1):
            excel_cells = list(worksheet[row_number])
            populated = [cell for cell in excel_cells if cell.value not in (None, "")]
            if not populated and row_number not in merged_rows:
                continue
            values = [_text(cell.value) for cell in populated]
            row_dimension = worksheet.row_dimensions[row_number]
            row = BudgetTemplateRow.objects.create(
                sheet=sheet,
                row_number=row_number,
                row_type=_row_type(
                    values,
                    sum(1 for cell in populated if cell.font.bold),
                    row_number in merged_rows,
                ),
                label=" | ".join(values[:4])[:500],
                account=_account_match(values, accounts_by_code, accounts_by_name),
                is_included=bool(populated),
                height=row_dimension.height,
                is_hidden=bool(row_dimension.hidden),
            )
            for cell in populated:
                raw_value = _text(cell.value)
                formula = raw_value if cell.data_type == "f" or raw_value.startswith("=") else ""
                BudgetTemplateCell.objects.create(
                    row=row,
                    column=columns[cell.column],
                    coordinate=cell.coordinate,
                    raw_value=raw_value,
                    formula=formula,
                    data_type=cell.data_type or "",
                    number_format=cell.number_format or "",
                    style_metadata=_style(cell),
                )
    workbook.close()
    return template
