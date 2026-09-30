"""PHASE 8 — Import Pipeline services.

Flow: Extract (CSV/Excel via pandas · PDF via pdfplumber, OCR optional layer)
→ Preview → Field Mapping → Validation (errors/warnings/duplicates)
→ User Confirmation → Import (atomic) → Import Log.

The original file is NEVER deleted. PDF data NEVER goes straight to the DB.
"""
from __future__ import annotations

import io
import re
import shutil
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

MAX_FILE_MB = 10
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


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Auto-suggest target←source mapping from header names (ar/en aliases)."""
    normed = {_norm(h): h for h in headers}
    mapping: dict[str, str] = {}
    for key, _label in TARGET_FIELDS:
        hit = ""
        for alias in _ALIASES[key]:
            if _norm(alias) in normed:
                hit = normed[_norm(alias)]
                break
        mapping[key] = hit
    return mapping


# ---------------------------------------------------------------- extraction
def _records_from_df(df: pd.DataFrame) -> tuple[list[str], list[dict]]:
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
    try:
        df = pd.read_excel(fileobj, dtype=str, keep_default_na=False)
    except Exception as exc:  # noqa: BLE001 — surface as Arabic form error
        raise ValidationError(
            "تعذّر قراءة ملف Excel — تأكد أنه بصيغة xlsx سليمة. "
            f"({type(exc).__name__})")
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
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in table:
                    table_rows.append([
                        str(c).strip() if c is not None else "" for c in row])
        if table_rows:
            headers = table_rows[0]
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
            if job.file_format == "csv":
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
    job.column_map = suggest_mapping(headers) if headers else {}
    job.log("extract_completed", rows=len(rows), columns=len(headers),
            warnings=len(warnings))
    job.save()


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


def validate_job(job: ImportJob, user, *, request=None) -> dict:
    """Apply mapping → per-row validation → summary. Saves `job`."""
    if job.status not in (ImportJob.STATUS_EXTRACTED,
                          ImportJob.STATUS_VALIDATED):
        raise ValidationError("لا يمكن التحقق إلا بعد الاستخراج بنجاح.")
    if not job.rows:
        raise ValidationError(
            "لا توجد صفوف في الملف — استُخرج صفوف صفرية."
            + (" ".join(job.extraction_warnings or [])))
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
def run_import(job: ImportJob, user, *, request=None) -> int:
    """Confirmation step — insert ONLY valid rows, atomically, then log."""
    if job.status != ImportJob.STATUS_VALIDATED:
        raise ValidationError(
            "لا يمكن التنفيذ قبل التحقق من البيانات واعتماد المطابقة.")
    valid_rows = [r for r in job.rows if r.get("valid")]
    if not valid_rows:
        raise ValidationError("لا توجد صفوف صالحة للاستيراد.")

    imported = 0
    with transaction.atomic():
        for row in valid_rows:
            ready = row["ready"]
            period = MonthlyPeriod.objects.get(pk=ready["period_id"])
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
                "summary": {k: job.summary.get(k) for k in
                            ("total", "valid", "invalid", "duplicate")},
            },
            request=request,
            actor=user,
        )
    return imported


def cancel_job(job: ImportJob, user, *, request=None) -> None:
    """Cancel a job — the original file is kept as evidence, always."""
    if job.status in (ImportJob.STATUS_COMPLETED,):
        raise ValidationError("لا يمكن إلغاء عملية مكتملة.")
    job.status = ImportJob.STATUS_CANCELLED
    job.log("cancelled", by=getattr(user, "username", ""))
    job.save()
    log_action(
        action="entity_updated", entity_type="import_job", entity_id=job.pk,
        diff={"status": job.status}, request=request, actor=user)
