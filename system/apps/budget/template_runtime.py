"""Runtime calculations for Excel-originated flexible budget sheets."""
from __future__ import annotations

import ast
import operator
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from openpyxl.utils.cell import range_boundaries

from .models import BudgetTemplateColumn, BudgetTemplateRow


ZERO = Decimal("0")
MONEY = Decimal("0.01")
CELL_REF = re.compile(r"(?<![A-Z0-9_])\$?([A-Z]{1,3})\$?(\d+)", re.I)
SUM_CALL = re.compile(r"SUM\(([^()]*)\)", re.I)
PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")

BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def to_decimal(value) -> Decimal:
    if value in (None, ""):
        return ZERO
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return ZERO


def money(value) -> Decimal:
    return to_decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        right = _safe_eval(node.right)
        if isinstance(node.op, ast.Div) and right == ZERO:
            return ZERO
        return BIN_OPS[type(node.op)](_safe_eval(node.left), right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
        return UNARY_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported formula expression")


class SheetRuntime:
    def __init__(self, sheet):
        self.sheet = sheet
        self.cells = {
            cell.coordinate.upper(): cell
            for row in sheet.rows.prefetch_related("cells").all()
            for cell in row.cells.all()
        }
        self.cache = {}

    def value(self, coordinate, stack=None):
        coordinate = coordinate.replace("$", "").upper()
        if coordinate in self.cache:
            return self.cache[coordinate]
        cell = self.cells.get(coordinate)
        if cell is None:
            return ZERO
        if not cell.formula:
            value = to_decimal(cell.effective_value)
            self.cache[coordinate] = value
            return value
        stack = set(stack or ())
        if coordinate in stack:
            return ZERO
        stack.add(coordinate)
        value = self.evaluate_formula(cell.formula, stack)
        self.cache[coordinate] = value
        return value

    def _sum_argument(self, argument, stack):
        argument = argument.strip()
        if ":" in argument and "!" not in argument:
            try:
                min_col, min_row, max_col, max_row = range_boundaries(
                    argument.replace("$", ""),
                )
            except ValueError:
                return ZERO
            total = ZERO
            from openpyxl.utils import get_column_letter
            for row in range(min_row, max_row + 1):
                for column in range(min_col, max_col + 1):
                    total += self.value(f"{get_column_letter(column)}{row}", stack)
            return total
        if CELL_REF.fullmatch(argument):
            return self.value(argument, stack)
        return to_decimal(argument)

    def evaluate_formula(self, formula, stack=None):
        expression = str(formula or "").strip().lstrip("=")
        if not expression or "!" in expression or "#" in expression:
            return ZERO
        stack = set(stack or ())
        while True:
            match = SUM_CALL.search(expression)
            if not match:
                break
            args = re.split(r"[,;]", match.group(1))
            total = sum((self._sum_argument(arg, stack) for arg in args), ZERO)
            expression = expression[:match.start()] + str(total) + expression[match.end():]
        expression = PERCENT.sub(lambda match: f"({match.group(1)}/100)", expression)
        expression = CELL_REF.sub(
            lambda match: str(self.value(f"{match.group(1)}{match.group(2)}", stack)),
            expression,
        ).replace("^", "**")
        try:
            return _safe_eval(ast.parse(expression, mode="eval"))
        except (SyntaxError, ValueError, TypeError, InvalidOperation, OverflowError):
            return ZERO

    def display_value(self, cell):
        if cell is None:
            return ""
        if cell.formula:
            return str(money(self.value(cell.coordinate)))
        return cell.effective_value


def _row_months(row, runtime, columns):
    cells = {cell.column_id: cell for cell in row.cells.all()}
    monthly = {month: ZERO for month in range(1, 13)}
    monthly_found = False
    annual = ZERO
    annual_found = False
    for column in columns:
        cell = cells.get(column.pk)
        if column.role.startswith("month_"):
            month = int(column.role[-2:])
            monthly[month] = money(runtime.value(cell.coordinate) if cell else ZERO)
            monthly_found = True
        elif column.role == BudgetTemplateColumn.ROLE_ANNUAL and not annual_found:
            annual = money(runtime.value(cell.coordinate) if cell else ZERO)
            annual_found = True
    if monthly_found:
        annual = money(sum(monthly.values(), ZERO))
    elif annual_found and annual:
        share = (annual / Decimal("12")).quantize(MONEY, rounding=ROUND_HALF_UP)
        monthly = {month: share for month in range(1, 13)}
        monthly[12] += annual - sum(monthly.values(), ZERO)
    return monthly, annual


def template_monthly_output(sheet):
    runtime = SheetRuntime(sheet)
    columns = list(sheet.columns.all())
    rows = []
    queryset = sheet.rows.filter(
        is_included=True,
        analytical_account__isnull=False,
    ).select_related("main_account", "analytical_account").prefetch_related("cells")
    for row in queryset:
        monthly, annual = _row_months(row, runtime, columns)
        rows.append({
            "row": row,
            "main_account": row.main_account,
            "analytical_account": row.analytical_account,
            "months": monthly,
            "annual_amount": annual,
        })
    return rows


def template_summary_output(sheet):
    grouped = {}
    for item in template_monthly_output(sheet):
        account = item["main_account"]
        if account is None:
            continue
        target = grouped.setdefault(account.pk, {
            "main_account": account,
            "months": {month: ZERO for month in range(1, 13)},
            "annual_amount": ZERO,
        })
        for month, amount in item["months"].items():
            target["months"][month] += amount
        target["annual_amount"] += item["annual_amount"]
    return list(grouped.values())
