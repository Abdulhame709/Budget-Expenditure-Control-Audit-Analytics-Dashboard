"""PHASE 8 — Import Pipeline services.

Flow: Extract (CSV/Excel via pandas · PDF via pdfplumber, OCR optional layer)
→ Preview → Field Mapping → Validation (errors/warnings/duplicates)
→ User Confirmation → Import (atomic) → Import Log.

The original file is NEVER deleted. PDF data NEVER goes straight to the DB.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
from zipfile import ZipFile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.permissions import has_perm
from apps.expenses.models import Expense
from apps.expenses.services import next_expense_number
from apps.governance.services import log_action
from apps.imports.models import ImportJob
from apps.reference.models import Account, Department, MonthlyPeriod, Supplier
from apps.reference.services import require_period_postable
from apps.imports import targets as structured_targets

MAX_FILE_MB = 10
MAX_ROWS = 20_000
MAX_COLUMNS = 200
MAX_PDF_PAGES = 100
MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_MEMBERS = 2_000
ALLOWED_EXTENSIONS = {".csv": "csv", ".xlsx": "xlsx", ".pdf": "pdf"}

# ---------------------------------------------------------------- mapping
# target field → (label, aliases normalized by _norm)
TARGET_FIELDS: list[tuple[str, str]] = [
    ("expense_date", "تاريخ المصروف"),
    ("department", "الإدارة"),
    ("account", "الحساب"),
    ("description", "البيان / الوصف"),
    ("amount", "المبلغ"),
    ("supplier", "المورّد"),
    ("invoice_reference", "رقم الفاتورة"),
    ("currency", "العملة"),
    ("payment_method", "طريقة الدفع"),
    ("payment_reference", "مرجع الدفع"),
    ("approval_reference", "مرجع الاعتماد"),
    ("expense_number", "رقم المصروف"),
]
_REQUIRED = ("expense_date", "department", "account", "description", "amount")

_ALIASES: dict[str, tuple[str, ...]] = {
    "expense_date": ("date", "expense date", "expense date", "التاريخ",
                     "تاريخ المصروف", "تاريخ"),
    "department": ("department", "dept", "الادارة", "الإدارة", "الجهة"),
    "account": ("account", "account code", "code", "الحساب", "رقم الحساب",
                "كود الحساب"),
    "description": ("description", "desc", "details", "البيان", "الوصف",
                    "الوصف والبيان", "بيان"),
    "amount": ("amount", "amt", "value", "المبلغ", "القيمة", "amount usd"),
    "supplier": ("supplier", "vendor", "المورد", "المورّد", "اسم المورد"),
    "invoice_reference": ("invoice", "invoice no", "invoice number",
                          "رقم الفاتورة", "الفاتورة", "مرجع الفاتورة"),
    "currency": ("currency", "curr", "العملة"),
    "payment_method": ("payment method", "payment", "طريقة الدفع", "الدفع"),
    "payment_reference": ("payment reference", "ref", "مرجع الدفع", "المرجع"),
    "approval_reference": ("approval", "approval ref", "معتمد", "الاعتماد",
                           "مرجع الاعتماد", "رقم الاعتماد"),
    "expense_number": ("expense number", "expense no", "رقم المصروف",
                       "الرقم"),
}


def _norm(value: str) -> str:
    """Normalize a header/alias: lowercase, Arabic alef variants, no spaces."""
    s = str(value or "").strip().lower()
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[\s_\-./()]+", "", s)
    return s


def detect_format(filename: str) -> str:
    """Return 'csv'|'xlsx'|'pdf' — raises Arabic ValueError when unsupported."""
    from pathlib import Path
    ext = Path(str(filename or "")).suffix.lower()
    fmt = ALLOWED_EXTENSIONS.get(ext)
    if not fmt:
        raise ValidationError(
            "صيغة الملف غير مدعومة — المسموح: CSV و Excel (xlsx) و PDF.")
    return fmt


_DETAILED_BUDGET_FIELDS: list[tuple[str, str]] = [
    ("fiscal_year", "السنة المالية"),
    ("budget_name", "اسم الموازنة"),
    ("version", "رقم النسخة"),
    ("currency", "العملة"),
    ("_archive_only", "أرشفة فقط — لا تُنشأ سطور موازنة شهرية"),
]


def get_target_fields(target: str) -> list[tuple[str, str]]:
    if target in (ImportJob.TARGET_BUDGET_MATRIX, ImportJob.TARGET_ACTUAL_MATRIX):
        from apps.imports.matrix import FIELDS
        return FIELDS
    if target == ImportJob.TARGET_EXPENSES:
        return TARGET_FIELDS
    if target == ImportJob.TARGET_DETAILED_BUDGET:
        return _DETAILED_BUDGET_FIELDS
    return structured_targets.target_fields(target)


def get_required_fields(target: str):
    if target in (ImportJob.TARGET_BUDGET_MATRIX, ImportJob.TARGET_ACTUAL_MATRIX):
        from apps.imports.matrix import FIELDS
        return tuple(key for key, _ in FIELDS)
    if target == ImportJob.TARGET_EXPENSES:
        return _REQUIRED
    if target == ImportJob.TARGET_DETAILED_BUDGET:
        return ()
    return structured_targets.required_fields(target)


_DETAILED_BUDGET_ALIASES: dict[str, tuple[str, ...]] = {
    "fiscal_year": ("fiscal year", "year", "السنة المالية", "السنة"),
    "budget_name": ("budget name", "name", "اسم الموازنة", "اسم الميزانية", "الموازنة"),
    "version": ("version", "رقم النسخة", "الإصدار"),
    "currency": ("currency", "curr", "العملة"),
    "_archive_only": (),
}


def suggest_mapping(headers: list[str], target: str = ImportJob.TARGET_EXPENSES) -> dict[str, str]:
    """Auto-suggest target←source mapping from header names (ar/en aliases)."""
    normed = {_norm(h): h for h in headers}
    if target in (ImportJob.TARGET_BUDGET_MATRIX, ImportJob.TARGET_ACTUAL_MATRIX):
        from apps.imports.matrix import FIELDS
        return {key: header for (key, _), header in zip(FIELDS, headers)} if len(headers) == 14 else {}
    mapping: dict[str, str] = {}
    fields = get_target_fields(target)
    if target == ImportJob.TARGET_EXPENSES:
        aliases = _ALIASES
    elif target == ImportJob.TARGET_DETAILED_BUDGET:
        aliases = _DETAILED_BUDGET_ALIASES
    else:
        aliases = structured_targets.target_aliases(target)
    for key, _label in fields:
        hit = ""
        for alias in aliases[key]:
            if _norm(alias) in normed:
                hit = normed[_norm(alias)]
                break
        mapping[key] = hit
    return mapping


_AR_LABELS_BY_NORM: dict[str, str] = {}


def _all_target_labels() -> dict[str, str]:
    """normalized Arabic label → label, lazily built once across all targets."""
    global _AR_LABELS_BY_NORM
    if _AR_LABELS_BY_NORM:
        return _AR_LABELS_BY_NORM
    labels: dict[str, str] = {}
    for target_key, _target_label in ImportJob.TARGET_CHOICES:
        for _key, label in get_target_fields(target_key):
            labels.setdefault(_norm(label), label)
    _AR_LABELS_BY_NORM = labels
    return labels


def header_labels(headers: list[str], target: str) -> dict[str, str]:
    """Arabic display label per raw file header (preview + mapping UI).

    1) exact match of the header against the target's Arabic labels
    2) exact match against a known alias (Arabic or English) → Arabic label
    3) fallback: the raw header unchanged (dir="ltr" keeps it readable).
    """
    target_fields = get_target_fields(target)
    if target in (ImportJob.TARGET_BUDGET_MATRIX, ImportJob.TARGET_ACTUAL_MATRIX):
        return {header: label for (_, label), header in zip(target_fields, headers)}
    by_label = {_norm(label): label for _key, label in target_fields}
    if target == ImportJob.TARGET_EXPENSES:
        aliases = _ALIASES
    elif target == ImportJob.TARGET_DETAILED_BUDGET:
        aliases = _DETAILED_BUDGET_ALIASES
    else:
        aliases = structured_targets.target_aliases(target)
    alias_to_label = {_norm(alias): label
                      for key, label in target_fields
                      for alias in aliases.get(key, ())}
    all_labels = _all_target_labels()
    display: dict[str, str] = {}
    for header in headers:
        normalized = _norm(header)
        display[header] = (by_label.get(normalized) or alias_to_label.get(normalized)
                           or all_labels.get(normalized) or header)
    return display


def build_template_csv(target: str) -> str:
    """CSV template with Arabic column headers (✓ = required) + a hint row."""
    fields = get_target_fields(target)
    required = set(get_required_fields(target))
    header_row = ["✓ " + label if key in required else label
                  for key, label in fields]
    hint_row = ["إلزامي" if key in required else "اختياري"
                for key, _label in fields]
    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM so Excel opens العربية correctly
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header_row)
    writer.writerow(hint_row)
    return buf.getvalue()


def build_accounts_template_xlsx() -> bytes:
    """Excel template matching the approved 2026 chart-of-accounts workbook."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "دليل الحسابات"
    headers = [label for _key, label in get_target_fields("accounts")]
    sheet.append(headers)
    sheet.sheet_view.rightToLeft = True
    sheet.freeze_panes = "A2"
    fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")
    widths = [18, 20, 38, 12, 14, 20, 24, 24]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


# ---------------------------------------------------------------- multi-sheet budget archive
def _looks_numeric_value(v):
    from decimal import Decimal, InvalidOperation
    if v in (None, ""):
        return False
    s = str(v).strip().replace(",", "")
    if not s:
        return False
    try:
        Decimal(s)
        return True
    except (InvalidOperation, ValueError):
        return False


def _row_numeric_ratio(cells) -> float:
    non_empty = [c for c in cells if c != ""]
    if not non_empty:
        return 0.0
    numeric = sum(1 for c in non_empty if _looks_numeric_value(c))
    return numeric / len(non_empty)


def _extract_detailed_budget(fileobj):
    """Parse every sheet of an xlsx workbook, preserving the long Arabic title
    (merged across all visible columns) and promoting the first structured row
    into the table header."""
    import openpyxl
    from decimal import Decimal

    fileobj.seek(0)
    try:
        wb = openpyxl.load_workbook(fileobj, data_only=True, read_only=True)
    except Exception as exc:
        raise ValidationError(f"تعذّر فتح مصنّف Excel: {type(exc).__name__}") from exc

    sheets, warnings = [], []
    grand_total = Decimal("0")
    for index, sheet in enumerate(wb.worksheets, start=1):
        if sheet.max_column > MAX_COLUMNS or sheet.max_row > MAX_ROWS * 5:
            raise ValidationError(
                f"ورقة «{sheet.title}» تتجاوز حدود الأعمدة/الصفوف المسموحة.")
        rows_raw = [["" if v is None else str(v).strip() for v in row]
                    for row in sheet.iter_rows(values_only=True)]
        while rows_raw and not any(rows_raw[0]):
            rows_raw.pop(0)
        while rows_raw and not any(rows_raw[-1]):
            rows_raw.pop()
        if not rows_raw:
            sheets.append({"name": sheet.title, "order": index, "headers": [],
                            "rows": [], "total": None})
            continue

        # merge consecutive leading text-only title rows into one display title
        def _non_empty(r):
            return [c for c in r if c != ""]
        titles = []
        while rows_raw:
            ne = _non_empty(rows_raw[0])
            # a title row: very sparse (1-2 cells) and purely textual
            if (ne and len(ne) <= 2
                    and not any(_looks_numeric_value(c) for c in ne)):
                titles.extend(ne)
                rows_raw.pop(0)
                continue
            break
        sheet_title = " — ".join(titles) if titles else sheet.title

        # ---- per-row alignment pass -----------------------------------
        # For irregular sheets (e.g. اعياد 2025) the title/header may start
        # later than the data (because the header row uses a merged region).
        # Record each row's first non-empty column NOW (after title pop) so
        # we can later re-align header vs body on the same starting column.
        def _lead(r):
            i = 0
            while i < len(r) and r[i] == "":
                i += 1
            return i
        row_leads = [_lead(r) for r in rows_raw]

        # Trim fully-empty LEADING columns globally (titles/headers are often
        # merged, so column trimming must not drop populated leftmost columns).
        lead = 0
        width = max((len(r) for r in rows_raw), default=0)
        while lead < width and all(len(r) <= lead or r[lead] == "" for r in rows_raw):
            lead += 1
        if lead:
            rows_raw = [r[lead:] for r in rows_raw]
            row_leads = [mx - lead for mx in row_leads]

        # Trim fully-empty TRAILING columns across all rows
        used = max((len(r) for r in rows_raw), default=0)
        while used > 0 and all(len(r) <= used - 1 or r[used - 1] == "" for r in rows_raw):
            used -= 1
        rows_raw = [(r + [""] * used)[:used] for r in rows_raw]

        header, body, header_candidate = [], rows_raw, False
        if rows_raw:
            first = rows_raw[0]
            width = max(len(r) for r in rows_raw)

            def _looks_label(s: str) -> bool:
                # sequential markers (1 / أ / A) and bare numbers are data, not labels
                if _looks_numeric_value(s):
                    return False
                if len(s) <= 2:
                    return False
                return True

            # Sheet type detection:
            #  - "listical" (no real header): like simple lists of (label, amount) pairs.
            #  - "tabular"  (real header row exists): first row has ≥2 label-like cells.
            #
            # A row is only a header if:
            #     * it has at least 2 textual label cells, AND
            #     * its numeric content is in trailing positions (so the header row isn't data)
            text_cells = [c for c in first if _looks_label(c)]
            col2_numeric = (len(first) >= 2 and _looks_numeric_value(first[1]))
            header_candidate = (len(text_cells) >= 2
                                and not col2_numeric
                                and _row_numeric_ratio(first) <= 0.4)

            if header_candidate:
                header = first
                body = rows_raw[1:]
                # Header row already spans the full trimmed width. When the
                # header leaves the first 1-2 cells blank but body rows put a
                # section label + sequence number there, give them semantic names.
                if row_leads and row_leads[0] > 0 and body:
                    body0 = body[0]
                    # pattern: body[0] col0 = section text, col1 = sequence number
                    if (len(body0) >= 2 and body0[0] and not _looks_numeric_value(body0[0])
                            and _looks_numeric_value(body0[1] if len(body0) > 1 else "")):
                        header = ["القسم", "م", *header[2:]]
                    elif not body0[0]:
                        pass  # keep عمود N fallbacks
            else:
                # Simple list sheet — synthesize a bilingual-aware header row.
                # Map count: 2 cols → (البيان, المبلغ); 3 cols → (البيان, المبلغ, ملاحظات);
                #            ≥4 cols → (البيان, المبلغ, ملاحظات, عمود 4, عمود 5, …)
                base = ["البيان", "المبلغ", "ملاحظات"]
                header = base[:width] if width <= len(base) else (
                         base + [f"عمود {i + len(base) + 1}" for i in range(width - len(base))])

            # Align header width with body width — pad on the LEFT with generic
            # labels when header is shorter (common when first column(s) contain
            # section data that the header row didn't name explicitly).
            body_w = max((len(r) for r in body), default=0)
            if header and len(header) < body_w:
                header = [f"عمود {i + 1}" for i in range(body_w - len(header))] + header

            # Normalize / deduplicate header labels (avoid confusion in display).
            headers_norm = []
            seen = {}
            for i, h in enumerate(header):
                key = (h or "").strip() or f"عمود {i + 1}"
                if key in seen:
                    seen[key] += 1
                    headers_norm.append(f"{key} ({seen[key]})")
                else:
                    seen[key] = 1
                    headers_norm.append(key)
            header = headers_norm

        # Compute sheet total
        total = None
        if not header_candidate:
            # LIST sheet: sum the "المبلغ" column (column index 1)
            amount_idx = 1
            s = Decimal("0")
            seen = False
            for row_vals in body:
                if len(row_vals) > amount_idx and _looks_numeric_value(row_vals[amount_idx]):
                    try:
                        s += Decimal(row_vals[amount_idx].replace(",", ""))
                        seen = True
                    except Exception:
                        pass
            if seen:
                total = s
        else:
            # TABULAR sheet: prefer a row containing "إجمالي" / "المجموع" / مجموع
            # (take the LAST such row, scanning from bottom); take its largest numeric cell.
            for row_vals in reversed(body):
                text = [c for c in row_vals if c and not _looks_numeric_value(c)]
                if any(("إجمالي" in c or "المجموع" in c or "اجمالي" in c) for c in text):
                    numeric = [c for c in row_vals if _looks_numeric_value(c)]
                    if numeric:
                        try:
                            total = Decimal(str(max(float(c.replace(",", "")) for c in numeric)))
                            break
                        except Exception:
                            pass
            if total is None and body:
                # fallback: largest numeric cell of the last row that has numbers
                for row_vals in reversed(body):
                    numeric = [c for c in row_vals if _looks_numeric_value(c)]
                    if numeric:
                        try:
                            total = Decimal(str(max(float(c.replace(",", "")) for c in numeric)))
                            break
                        except Exception:
                            pass
        if total is not None:
            grand_total = grand_total + total
        sheets.append({"name": sheet.title, "display_title": sheet_title or sheet.title,
                        "order": index, "headers": header, "rows": body,
                        "has_real_header": bool(header_candidate),
                        "total": (str(total) if total is not None else None)})

    preview_headers = sheets[0]["headers"] if sheets else []
    preview_rows = []
    for s in sheets[:1]:
        for i, r in enumerate(s["rows"][:20], start=1):
            preview_rows.append({"sheet": s["name"], **{h: c for h, c in zip(s["headers"], r)}})
    return sheets, preview_headers, preview_rows, warnings, grand_total


# ---------------------------------------------------------------- extraction
def _records_from_df(df: pd.DataFrame) -> tuple[list[str], list[dict]]:
    if df.shape[1] > MAX_COLUMNS:
        raise ValidationError(f"عدد الأعمدة يتجاوز الحد المسموح ({MAX_COLUMNS}).")
    if df.shape[0] > MAX_ROWS:
        raise ValidationError(f"عدد الصفوف يتجاوز الحد المسموح ({MAX_ROWS}).")
    headers = [str(h).strip() for h in df.columns]
    rows: list[dict] = []
    for rec in df.to_dict(orient="records"):
        clean = {}
        empty = True
        for h, v in zip(df.columns, rec.values()):
            s = str(v).strip() if v is not None else ""
            if s:
                empty = False
            clean[str(h).strip()] = s
        if not empty:
            rows.append(clean)
    return headers, rows


def _extract_csv(fileobj) -> tuple[list[str], list[dict]]:
    raw = fileobj.read()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValidationError("تعذّر فك ترميز ملف CSV — جرّب UTF-8 أو cp1256.")
    first = text.splitlines()[0] if text.splitlines() else ""
    counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
    sep = max(counts, key=counts.get) if max(counts.values()) > 0 else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str,
                     keep_default_na=False, skip_blank_lines=True)
    return _records_from_df(df)


def _extract_excel(fileobj) -> tuple[list[str], list[dict]]:
    raw = fileobj.read()
    fileobj.seek(0)
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > MAX_XLSX_MEMBERS:
                raise ValidationError("ملف Excel يحتوي عناصر أكثر من الحد المسموح.")
            if sum(member.file_size for member in members) > MAX_XLSX_UNCOMPRESSED_BYTES:
                raise ValidationError("حجم محتوى Excel بعد فك الضغط يتجاوز الحد المسموح.")
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ValidationError("ملف Excel لا يحتوي بنية xlsx صالحة.")
        df = pd.read_excel(io.BytesIO(raw), dtype=str, keep_default_na=False)
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 — Arabic form error
        raise ValidationError(
            "تعذّر قراءة ملف Excel — تأكد أنه بصيغة xlsx سليمة. "
            f"({type(exc).__name__})") from exc
    return _records_from_df(df)


def _ocr_available() -> bool:
    """OCR is an OPTIONAL layer — never a requirement for the system."""
    if not shutil.which("tesseract"):
        return False
    try:  # noqa: PERF401
        import pytesseract  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _extract_pdf(fileobj) -> tuple[list[str], list[dict], list[str], bool]:
    """PDF → rows (tables first, then delimited text). OCR only if available.

    PDF rows NEVER touch the DB directly — they flow through the same
    Preview → Mapping → Validation → Confirmation pipeline.
    """
    import pdfplumber

    warnings: list[str] = []
    fileobj.seek(0)
    table_rows: list[list[str]] = []
    with pdfplumber.open(fileobj) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise ValidationError(
                f"عدد صفحات PDF يتجاوز الحد المسموح ({MAX_PDF_PAGES})."
            )
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in table:
                    table_rows.append([
                        str(c).strip() if c is not None else "" for c in row])
                    if len(table_rows) > MAX_ROWS + 1:
                        raise ValidationError(
                            f"عدد صفوف PDF يتجاوز الحد المسموح ({MAX_ROWS})."
                        )
        if table_rows:
            headers = table_rows[0]
            if len(headers) > MAX_COLUMNS:
                raise ValidationError(
                    f"عدد الأعمدة يتجاوز الحد المسموح ({MAX_COLUMNS})."
                )
            rows = []
            for raw in table_rows[1:]:
                cells = list(raw) + [""] * (len(headers) - len(raw))
                rec = dict(zip(headers, cells[:len(headers)]))
                if any(rec.values()):
                    rows.append(rec)
            return headers, rows, warnings, False

        text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for delim in ("|", "\t", ";", ","):
        parts = [ln.split(delim) for ln in lines]
        if len(parts) >= 2 and all(len(p) >= 2 for p in parts):
            width = max(len(p) for p in parts)
            if width > MAX_COLUMNS or len(parts) - 1 > MAX_ROWS:
                raise ValidationError("يتجاوز ملف PDF حدود الصفوف أو الأعمدة المسموحة.")
            headers = [c.strip() for c in (parts[0] + [""] * width)[:width]]
            rows = []
            for p in parts[1:]:
                cells = [c.strip() for c in p] + [""] * width
                rec = dict(zip(headers, cells[:width]))
                if any(rec.values()):
                    rows.append(rec)
            return headers, rows, warnings, False

    # no structured content → optional OCR layer (never mandatory)
    if _ocr_available():
        warnings.append(
            "لم يُعثر على جدول/نص منظم — استُخدمت طبقة OCR الاختيارية.")
        # OCR of scanned PDFs requires image rendering; treat as unavailable
        # here to keep the pipeline deterministic — the layer stays optional.
        warnings.append(
            "OCR متاح لكن لا يُطبَّق على هذا الملف تلقائيًا — "
            "صدِّر الجدول CSV أو استخرج النص يدويًا للمراجعة.")
    else:
        warnings.append(
            "لا توجد جداول/نص قابل للاستخراج في ملف PDF — طبقة OCR "
            "اختيارية وغير متاحة حاليًا (تثبيت tesseract + pytesseract "
            "يفعّلها). النظام الأساسي لا يعتمد على OCR.")
    return [], [], warnings, False


def extract_job(job: ImportJob) -> None:
    """Extract rows from the uploaded file into `job.rows` (never the DB)."""
    job.log("extract_started", fmt=job.file_format)
    try:
        job.source_file.open("rb")
        fileobj = job.source_file.file
        try:
            if job.target == ImportJob.TARGET_DETAILED_BUDGET:
                if job.file_format != "xlsx":
                    raise ValidationError(
                        "الموازنة التفصيلية الأولية تُستورد من ملف Excel (xlsx) فقط.")
                sheets, headers, rows, warnings, grand_total = _extract_detailed_budget(fileobj)
                ocr = False
                job.extraction_warnings = (job.extraction_warnings or []) + warnings
                job.summary = {"total": sum(len(s["rows"]) for s in sheets),
                               "valid": sum(len(s["rows"]) for s in sheets),
                               "invalid": 0, "duplicate": 0, "errors": 0,
                               "warnings": 0, "error_list": [], "warning_list": [],
                               "grand_total": str(grand_total)}
            elif job.file_format == "csv":
                headers, rows = _extract_csv(fileobj)
                warnings, ocr = [], False
            elif job.file_format == "xlsx":
                headers, rows = _extract_excel(fileobj)
                warnings, ocr = [], False
            else:
                headers, rows, warnings, ocr = _extract_pdf(fileobj)
        finally:
            job.source_file.close()
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        job.status = ImportJob.STATUS_FAILED
        job.log("extract_failed", error=str(exc)[:300])
        job.save(update_fields=["status", "job_log", "updated_at"])
        raise ValidationError(f"فشل استخراج الملف: {type(exc).__name__}") from exc

    job.headers = headers
    job.rows = [
        {"index": i, "source": r, "mapped": {}, "ready": {},
         "errors": [], "warnings": [], "duplicate": False, "valid": False}
        for i, r in enumerate(rows, start=1)
    ]
    job.extraction_warnings = warnings
    job.ocr_used = ocr
    job.status = ImportJob.STATUS_EXTRACTED
    job.column_map = suggest_mapping(headers, job.target) if headers else {}
    job.log("extract_completed", rows=len(rows), columns=len(headers),
            warnings=len(warnings))
    job.save()


def validate_job(job, user, request=None):
    if job.target in (ImportJob.TARGET_BUDGET_MATRIX, ImportJob.TARGET_ACTUAL_MATRIX):
        from apps.imports.matrix import validate_matrix
        return validate_matrix(job, user, request=request)
    if job.target == ImportJob.TARGET_DETAILED_BUDGET:
        # archive only — no row-wise mapping needed; sheets already extracted
        job.status = ImportJob.STATUS_VALIDATED
        job.log("validation_skipped_archive", sheets=len(job.detailed_sheets.all() if job.pk else []))
        job.save(update_fields=["status", "job_log", "updated_at"])
        return job.summary or {"total": len(job.rows), "valid": len(job.rows),
                                "invalid": 0, "duplicate": 0, "errors": 0,
                                "warnings": 0, "error_list": [], "warning_list": []}
    return _validate_job_original(job, user, request=request)


def run_import(job, user, request=None):
    if job.target in (ImportJob.TARGET_BUDGET_MATRIX, ImportJob.TARGET_ACTUAL_MATRIX):
        from apps.imports.matrix import import_matrix
        return import_matrix(job, user, request=request)
    if job.target == ImportJob.TARGET_DETAILED_BUDGET:
        raise ValidationError(
            "الموازنة التفصيلية الأولية أرشيف مرجعي — لا تُنفَّذ إلى سطور موازنة "
            "شهرية من هنا. استخدم هدف «الموازنة التقديرية — السطور الشهرية» "
            "لإدخال البيانات التشغيلية.")
    return _run_import_original(job, user, request=request)


def archive_detailed_budget(job, sheets):
    """Persist extracted workbook sheets into DetailedBudgetSheet rows under this job."""
    from apps.imports.models import DetailedBudgetSheet
    DetailedBudgetSheet.objects.filter(job=job).delete()
    created = 0
    for order, s in enumerate(sheets, start=1):
        DetailedBudgetSheet.objects.create(
            job=job, name=s["name"], order=order,
            display_title=s.get("display_title", s["name"]),
            headers=s["headers"], rows=s["rows"],
            sheet_total=s["total"])
        created += 1
    return created


# ---------------------------------------------------------------- validation
def _parse_date(value: str) -> date:
    s = str(value).strip()
    if not s:
        raise ValidationError("التاريخ مطلوب.")
    # excel serial (days since 1899-12-30)
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        return (datetime(1899, 12, 30) + timedelta(days=int(float(s)))).date()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
                "%d/%m/%y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"تاريخ غير صالح: «{s}».")


def _parse_amount(value) -> Decimal:
    s = str(value).strip().replace(",", "").replace(" ", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if s.endswith(".0") and s.count(".") == 1 and len(s.split(".")[1]) == 2:
        pass  # keep 4500.00
    if not s:
        raise ValidationError("المبلغ مطلوب.")
    try:
        amount = Decimal(s)
    except InvalidOperation as exc:
        raise ValidationError(f"مبلغ غير صالح: «{value}».") from exc
    if amount <= 0:
        raise ValidationError("المبلغ يجب أن يكون موجبًا وأكبر من صفر.")
    return amount


_CURRENCY = {"USD", "SAR", "YER"}
_PAYMENT = {"cash": "cash", "transfer": "transfer", "check": "check",
            "other": "other",
            "نقدًا": "cash", "نقد": "cash", "cashly": "cash",
            "تحويل": "transfer", "تحويل بنكي": "transfer",
            "شيك": "check", "اخرى": "other", "أخرى": "other"}

_PERIOD_PROBLEM_MSG = (
    "التسجيل في فترة {problem} — يتطلب صلاحية «تسجيل في فترة مغلقة "
    "(تجاوز مُصرَّح)» (periods.post_closed).")


def _resolve(candidates: dict[str, object], value: str, label: str):
    key = _norm(value)
    if not key:
        raise ValidationError(f"{label} مطلوب.")
    obj = candidates.get(key)
    if obj is None:
        raise ValidationError(f"{label} «{value}» غير موجود في البيانات المرجعية.")
    return obj


def _lookup_maps():
    depts = {}
    for d in Department.objects.all():
        depts[_norm(d.code)] = d
        depts[_norm(d.name)] = d
    accs = {}
    for a in Account.objects.all():
        accs[_norm(a.code)] = a
        accs[_norm(a.name)] = a
    sups = {}
    for s in Supplier.objects.all():
        sups[_norm(s.code)] = s
        sups[_norm(s.name)] = s
    return depts, accs, sups


@transaction.atomic
def _validate_job_original(job: ImportJob, user, *, request=None) -> dict:
    """Apply mapping → per-row validation → summary under a row lock."""
    job = ImportJob.objects.select_for_update().get(pk=job.pk)
    if job.status not in (ImportJob.STATUS_EXTRACTED,
                          ImportJob.STATUS_VALIDATED):
        raise ValidationError("لا يمكن التحقق إلا بعد الاستخراج بنجاح.")
    if not job.rows:
        raise ValidationError(
            "لا توجد صفوف في الملف — استُخرج صفوف صفرية."
            + (" ".join(job.extraction_warnings or [])))
    if job.target != ImportJob.TARGET_EXPENSES:
        return structured_targets.validate_locked_job(job, user, _norm)
    mapping = {k: v for k, v in (job.column_map or {}).items() if v}
    missing = [f for f in _REQUIRED if f not in mapping]
    if missing:
        labels = dict(TARGET_FIELDS)
        raise ValidationError(
            "مطابقة الأعمدة غير مكتملة — الحقول المطلوبة بلا عمود: "
            + "، ".join(labels[f] for f in missing))

    depts, accs, sups = _lookup_maps()
    can_override = has_perm(user, "periods.post_closed")
    seen_keys: dict[tuple, int] = {}
    error_list: list[dict] = []
    warning_list: list[dict] = []
    n_errors = n_warnings = 0
    n_valid = n_invalid = n_dup = 0

    for row in job.rows:
        src = row["source"]
        errors: list[str] = []
        warnings: list[str] = []
        mapped = {k: (src.get(h) or "").strip() for k, h in mapping.items()}
        row["mapped"] = mapped
        ready: dict = {}

        # ---- date & period
        d = None
        try:
            d = _parse_date(mapped.get("expense_date", ""))
            ready["expense_date"] = d.isoformat()
        except ValidationError as exc:
            errors.append(f"تاريخ المصروف: {exc.messages[0]}")
        period = None
        if d:
            period = MonthlyPeriod.objects.filter(
                start_date__lte=d, end_date__gte=d).first()
            if period is None:
                errors.append(
                    f"تاريخ المصروف: لا توجد فترة شهرية تغطي التاريخ {d}.")
            else:
                ready["period_id"] = period.pk
                problems = []
                if period.is_closed:
                    problems.append("مغلقة")
                if not period.is_active:
                    problems.append("غير نشطة")
                if not period.fiscal_year.is_active:
                    problems.append("سنتها المالية غير نشطة")
                if problems:
                    msg = _PERIOD_PROBLEM_MSG.format(
                        problem=" و".join(problems))
                    if can_override:
                        warnings.append(f"الفترة: {msg}")
                    else:
                        errors.append(f"الفترة: {msg}")

        # ---- FK lookups (business rules re-checked by Expense.clean later)
        for key, cache, label in (("department", depts, "الإدارة"),
                                  ("account", accs, "الحساب"),
                                  ("supplier", sups, "المورّد")):
            value = mapped.get(key, "")
            if key == "supplier" and not value:
                ready[f"{key}_id"] = None
                continue
            try:
                obj = _resolve(cache, value, label)
                ready[f"{key}_id"] = obj.pk
            except ValidationError as exc:
                errors.append(f"{label}: {exc.messages[0]}")

        # ---- scalars
        try:
            ready["amount"] = str(_parse_amount(mapped.get("amount", "")))
        except ValidationError as exc:
            errors.append(f"المبلغ: {exc.messages[0]}")
        description = mapped.get("description", "")
        if not description:
            errors.append("البيان / الوصف: مطلوب.")
        ready["description"] = description
        currency = (mapped.get("currency") or "").strip().upper() or "USD"
        if currency not in _CURRENCY:
            errors.append(f"العملة: «{currency}» غير مدعومة (USD/SAR/YER).")
        ready["currency"] = currency
        pay_raw = (mapped.get("payment_method") or "").strip().lower() or "transfer"
        payment = _PAYMENT.get(pay_raw) or _PAYMENT.get(_norm(pay_raw))
        if payment is None:
            errors.append(
                f"طريقة الدفع: «{mapped.get('payment_method')}» غير معروفة.")
        ready["payment_method"] = payment or "transfer"
        ready["payment_reference"] = mapped.get("payment_reference", "")
        invoice = mapped.get("invoice_reference", "") or None
        ready["invoice_reference"] = invoice
        ready["approval_reference"] = mapped.get("approval_reference", "")
        ready["expense_number"] = mapped.get("expense_number", "")

        # ---- duplicate detection (in-file + vs DB)
        duplicate = False
        key = (ready.get("expense_date"), ready.get("department_id"),
               ready.get("account_id"), ready.get("supplier_id"),
               invoice, ready.get("amount"))
        if key in seen_keys and all(key[:3]) and (
                invoice or ready.get("supplier_id")):
            duplicate = True
            errors.append(
                f"مكرر داخل الملف — يطابق الصف {seen_keys[key]}.")
        elif invoice and ready.get("supplier_id"):
            if Expense.objects.filter(
                    supplier_id=ready["supplier_id"],
                    invoice_reference=invoice).exists():
                duplicate = True
                errors.append(
                    "مكرر في قاعدة البيانات — نفس المورّد ورقم الفاتورة "
                    "موجودان مسبقًا.")
        seen_keys.setdefault(key, row["index"])

        # ---- final business-rule pass through the real model
        if not errors:
            expense = _build_expense(ready, period=period)
            try:
                expense.full_clean()
                expense.expense_category = expense.account.expense_category
            except ValidationError as exc:
                if hasattr(exc, "error_dict"):
                    for field, msgs in exc.error_dict.items():
                        errors.extend(f"{field}: {m}" for m in msgs)
                else:
                    errors.extend(exc.messages)

        row["ready"] = ready
        row["errors"] = errors
        row["warnings"] = warnings
        row["duplicate"] = duplicate
        row["valid"] = not errors and not duplicate
        n_valid += row["valid"]
        if duplicate:
            n_dup += 1
        elif errors:
            n_invalid += 1
        for msg in errors:
            n_errors += 1
            if len(error_list) < 300:
                error_list.append({"row": row["index"], "message": msg})
        for msg in warnings:
            n_warnings += 1
            if len(warning_list) < 300:
                warning_list.append({"row": row["index"], "message": msg})

    job.column_map = mapping
    job.summary = {
        "total": len(job.rows),
        "valid": n_valid,
        "invalid": n_invalid,
        "duplicate": n_dup,
        "errors": n_errors,
        "warnings": n_warnings,
        "error_list": error_list,
        "warning_list": warning_list,
    }
    job.status = ImportJob.STATUS_VALIDATED
    job.log("validation_completed", **{
        k: job.summary[k] for k in
        ("total", "valid", "invalid", "duplicate", "errors", "warnings")})
    job.save()
    return job.summary


def _build_expense(ready: dict, *, period=None, number: str | None = None):
    return Expense(
        expense_number=(number if number is not None
                        else ready.get("expense_number", "")),
        expense_date=date.fromisoformat(ready["expense_date"]),
        period_id=ready.get("period_id"),
        department_id=ready.get("department_id"),
        account_id=ready.get("account_id"),
        supplier_id=ready.get("supplier_id"),
        description=ready.get("description", ""),
        amount=Decimal(ready["amount"]),
        currency=ready.get("currency", "USD"),
        payment_method=ready.get("payment_method", "transfer"),
        payment_reference=ready.get("payment_reference", "") or "",
        invoice_reference=ready.get("invoice_reference") or None,
        approval_reference=ready.get("approval_reference", "") or "",
    )


# ---------------------------------------------------------------- import run
@transaction.atomic
def _run_import_original(job: ImportJob, user, *, request=None) -> int:
    """Confirmation step — insert valid rows atomically while holding the job lock."""
    job = ImportJob.objects.select_for_update().get(pk=job.pk)
    if job.status != ImportJob.STATUS_VALIDATED:
        raise ValidationError(
            "لا يمكن التنفيذ قبل التحقق من البيانات واعتماد المطابقة.")
    if job.target != ImportJob.TARGET_EXPENSES:
        return structured_targets.run_locked_job(job, user, request=request)
    valid_rows = [row for row in job.rows if row.get("valid")]
    if not valid_rows:
        raise ValidationError("لا توجد صفوف صالحة للاستيراد.")

    imported = 0
    for row in valid_rows:
        ready = row["ready"]
        period = MonthlyPeriod.objects.select_for_update().select_related(
            "fiscal_year"
        ).get(pk=ready["period_id"])
        # Recheck period status and posting permission at commit time; validation
        # may have happened before the period was closed or deactivated.
        require_period_postable(
            user, period,
            purpose=f"استيراد الملف {job.original_filename}", request=request)
        number = ready.get("expense_number") or next_expense_number(
            date.fromisoformat(ready["expense_date"]))
        expense = _build_expense(ready, period=period, number=number)
        expense.full_clean()
        if not expense.expense_category_id:
            expense.expense_category = expense.account.expense_category
        if expense.approval_reference:
            expense.approved_by = user
            expense.approved_at = timezone.now()
        expense.save()
        imported += 1

    job.status = ImportJob.STATUS_COMPLETED
    job.imported_count = imported
    job.log("import_completed", imported=imported,
            skipped=len(job.rows) - imported)
    job.save()
    log_action(
        action="data_imported",
        entity_type="import_job",
        entity_id=job.pk,
        diff={
            "target": job.target,
            "file": job.original_filename,
            "imported": imported,
            "skipped": len(job.rows) - imported,
            "summary": {key: job.summary.get(key) for key in
                        ("total", "valid", "invalid", "duplicate")},
        },
        request=request,
        actor=user,
    )
    return imported


@transaction.atomic
def cancel_job(job: ImportJob, user, *, request=None) -> None:
    """Cancel a job once; retain the original file as evidence."""
    job = ImportJob.objects.select_for_update().get(pk=job.pk)
    if job.status == ImportJob.STATUS_COMPLETED:
        raise ValidationError("لا يمكن إلغاء عملية مكتملة.")
    if job.status == ImportJob.STATUS_CANCELLED:
        return
    job.status = ImportJob.STATUS_CANCELLED
    job.log("cancelled", by=getattr(user, "username", ""))
    job.save()
    log_action(
        action="entity_updated",
        entity_type="import_job",
        entity_id=job.pk,
        diff={"status": job.status},
        request=request,
        actor=user,
    )
