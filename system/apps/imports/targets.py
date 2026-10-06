"""Target-specific definitions and validation for operational imports."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.budget.models import Budget, BudgetLine, BudgetVersion, MONTH_FIELDS
from apps.governance.services import log_action
from apps.imports.models import ImportJob
from apps.procurement.models import Procurement, Quotation
from apps.reference.models import (
    Account,
    Department,
    ExpenseCategory,
    FiscalYear,
    MonthlyPeriod,
    Supplier,
)


def _f(key, label, *aliases):
    return (key, label, (key, label, *aliases))


TARGETS = {
    "fiscal_years": {
        "fields": [_f("code", "رمز السنة", "year code"), _f("name", "اسم السنة", "year name"),
                   _f("year", "السنة", "calendar year"), _f("start_date", "تاريخ البداية", "start date"),
                   _f("end_date", "تاريخ النهاية", "end date"), _f("is_active", "نشط", "active"),
                   _f("notes", "ملاحظات", "notes")],
        "required": ("code", "name", "year", "start_date", "end_date"),
    },
    "periods": {
        "fields": [_f("fiscal_year", "السنة المالية", "fiscal year"), _f("month", "الشهر", "month"),
                   _f("start_date", "تاريخ البداية", "start date"), _f("end_date", "تاريخ النهاية", "end date"),
                   _f("status", "الحالة", "status"), _f("is_active", "نشط", "active"),
                   _f("notes", "ملاحظات", "notes")],
        "required": ("fiscal_year", "month", "start_date", "end_date"),
    },
    "departments": {
        "fields": [_f("code", "رمز الإدارة", "department code", "dept code"),
                   _f("name", "اسم الإدارة", "department name", "dept name"),
                   _f("parent", "الإدارة الأم", "parent department"), _f("is_active", "نشط", "active"),
                   _f("notes", "ملاحظات", "notes")],
        "required": ("code", "name"),
    },
    "expense_categories": {
        "fields": [_f("code", "رمز التصنيف", "category code"), _f("name", "اسم التصنيف", "category name"),
                   _f("description", "الوصف", "description"), _f("is_active", "نشط", "active")],
        "required": ("code", "name"),
    },
    "accounts": {
        "fields": [
            _f("code", "رقم الحساب", "رمز الحساب", "account code"),
            _f("currencies", "العملة", "currency", "currencies"),
            _f("name", "اسم الحساب", "account name"),
            _f("level", "المستوى", "level"),
            _f("ledger_type", "النوع", "نوع الدليل", "ledger type"),
            _f("parent", "الحساب الرئيسي", "الحساب الأب", "parent account"),
            _f("inclusion", "التضمين", "inclusion"),
            _f("report_type", "نوع التقرير", "report type"),
        ],
        "required": ("code", "currencies", "name", "level", "ledger_type",
                     "parent", "inclusion", "report_type"),
    },
    "suppliers": {
        "fields": [_f("code", "رمز المورد", "supplier code", "vendor code"),
                   _f("name", "اسم المورد", "supplier name", "vendor name"),
                   _f("contact_person", "مسؤول التواصل", "contact person"), _f("phone", "الهاتف", "phone"),
                   _f("email", "البريد الإلكتروني", "email"), _f("tax_number", "الرقم الضريبي", "tax number"),
                   _f("address", "العنوان", "address"), _f("is_active", "نشط", "active"),
                   _f("notes", "ملاحظات", "notes")],
        "required": ("code", "name"),
    },
    "budget_lines": {
        "fields": [_f("fiscal_year", "السنة المالية", "fiscal year"), _f("budget_name", "اسم الموازنة", "budget name"),
                   _f("version", "رقم النسخة", "version"), _f("department", "الإدارة", "department"),
                   _f("account", "الحساب", "account"), _f("expense_category", "تصنيف المصروف", "expense category"),
                   *[_f(month, f"الشهر {index}", f"month {index}") for index, month in enumerate(MONTH_FIELDS, 1)],
                   _f("notes", "ملاحظات", "notes")],
        "required": ("fiscal_year", "budget_name", "department", "account", *MONTH_FIELDS),
    },
    "procurements": {
        "fields": [_f("reference_number", "رقم سجل المشتريات", "reference number"), _f("date", "التاريخ", "date"),
                   _f("department", "الإدارة", "department"), _f("supplier", "المورد", "supplier", "vendor"),
                   _f("account", "الحساب", "account"), _f("description", "الوصف", "description"),
                   _f("amount", "المبلغ", "amount"), _f("status", "الحالة", "status"),
                   _f("purchase_order", "أمر الشراء", "purchase order", "po"),
                   _f("approval_reference", "مرجع الاعتماد", "approval reference"),
                   _f("payment_method", "طريقة الدفع", "payment method"),
                   _f("payment_reference", "مرجع الدفع", "payment reference"), _f("notes", "ملاحظات", "notes")],
        "required": ("reference_number", "date", "department", "supplier", "account", "description", "amount"),
    },
    "quotations": {
        "fields": [_f("procurement", "رقم سجل المشتريات", "procurement", "procurement reference"),
                   _f("supplier", "المورد", "supplier", "vendor"), _f("amount", "قيمة العرض", "amount"),
                   _f("offer_date", "تاريخ العرض", "offer date"), _f("reference", "مرجع العرض", "reference"),
                   _f("notes", "ملاحظات", "notes")],
        "required": ("procurement", "supplier", "amount"),
    },
}


def target_fields(target):
    return [(key, label) for key, label, _aliases in TARGETS[target]["fields"]]


def required_fields(target):
    return TARGETS[target]["required"]


def target_aliases(target):
    return {key: aliases for key, _label, aliases in TARGETS[target]["fields"]}


def _date(value, label):
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValidationError(f"{label}: استخدم YYYY-MM-DD أو DD/MM/YYYY.")


def _decimal(value, label, *, allow_zero=False):
    try:
        number = Decimal(str(value or "0").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{label}: قيمة رقمية غير صالحة.")
    if number < 0 or (not allow_zero and number == 0):
        raise ValidationError(f"{label}: يجب أن تكون القيمة {'صفرًا أو موجبة' if allow_zero else 'موجبة'}.")
    return number


def _integer(value, label, default=None):
    if str(value or "").strip() == "" and default is not None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{label}: يجب أن تكون عددًا صحيحًا.")


def _boolean(value, default=True):
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "نعم", "نشط"}:
        return True
    if text in {"0", "false", "no", "n", "لا", "غير نشط"}:
        return False
    raise ValidationError("قيمة نعم/لا غير صالحة.")


def _account_code(value):
    code = str(value or "").strip()
    if code.endswith(".0") and code[:-2].isdigit():
        code = code[:-2]
    if not code or not code.isdigit():
        raise ValidationError("رقم الحساب: يجب أن يكون رقمًا صحيحًا دون فواصل.")
    return code


def _account_currencies(value):
    aliases = {"$": "USD", "USD": "USD", "SR": "SAR", "SAR": "SAR", "YER": "YER"}
    raw = str(value or "").upper().replace("؛", ",").replace(";", ",")
    codes = []
    for token in (part.strip() for part in raw.split(",")):
        if not token:
            continue
        code = aliases.get(token)
        if not code:
            raise ValidationError(f"العملة: الرمز «{token}» غير مدعوم.")
        if code not in codes:
            codes.append(code)
    if not codes:
        raise ValidationError("العملة: يجب تحديد عملة واحدة على الأقل.")
    return codes


def _prepare_account(values):
    text = lambda key: str(values.get(key, "") or "").strip()
    code = _account_code(text("code"))
    level = _integer(text("level"), "المستوى")
    if level not in range(1, 7):
        raise ValidationError("المستوى: القيمة المقبولة من 1 إلى 6.")
    ledger_map = {"رئيسي": "main", "رئيسى": "main", "MAIN": "main",
                  "فرعي": "sub", "فرعى": "sub", "SUB": "sub"}
    ledger_type = ledger_map.get(text("ledger_type").upper())
    if not ledger_type:
        raise ValidationError("النوع: استخدم «رئيسي» أو «فرعي».")
    report_raw = text("report_type").replace("العموميه", "العمومية")
    report_map = {"الميزانية العمومية": "balance_sheet", "أرباح وخسائر": "profit_loss",
                  "ارباح وخسائر": "profit_loss", "BALANCE_SHEET": "balance_sheet",
                  "PROFIT_LOSS": "profit_loss"}
    report_type = report_map.get(report_raw)
    if not report_type:
        raise ValidationError("نوع التقرير: استخدم «الميزانية العمومية» أو «أرباح وخسائر».")
    account_type = {"1": "asset", "2": "liability", "3": "expense", "4": "income"}.get(code[0])
    if not account_type:
        raise ValidationError("رقم الحساب: يجب أن يبدأ بأحد الأرقام 1 أو 2 أو 3 أو 4.")
    parent_value = text("parent")
    parent_code = "" if parent_value in {"", "0", "0.0"} else _account_code(parent_value)
    return {
        "code": code,
        "currencies": _account_currencies(text("currencies")),
        "name": text("name"),
        "level": level,
        "ledger_type": ledger_type,
        "parent_code": parent_code,
        "inclusion": text("inclusion"),
        "report_type": report_type,
        "account_type": account_type,
        "is_active": True,
    }


def _lookup(model, value, label, normalizer):
    wanted = normalizer(value)
    if not wanted:
        raise ValidationError(f"{label}: مطلوب.")
    for obj in model.objects.all():
        if normalizer(getattr(obj, "code", "")) == wanted or normalizer(getattr(obj, "name", "")) == wanted:
            return obj
    raise ValidationError(f"{label}: «{value}» غير موجود.")


def _errors(exc):
    if hasattr(exc, "message_dict"):
        return [f"{field}: {message}" for field, messages in exc.message_dict.items() for message in messages]
    return list(exc.messages)


def _serialize(data):
    return {key: value.isoformat() if isinstance(value, date) else str(value) if isinstance(value, Decimal) else value
            for key, value in data.items()}


def _prepare(target, values, normalizer):
    text = lambda key, default="": str(values.get(key, default) or default).strip()
    if target == "fiscal_years":
        data = {"code": text("code"), "name": text("name"), "year": _integer(text("year"), "السنة"),
                "start_date": _date(text("start_date"), "تاريخ البداية"),
                "end_date": _date(text("end_date"), "تاريخ النهاية"),
                "is_active": _boolean(text("is_active")), "notes": text("notes")}
        return FiscalYear, data, (data["code"],), FiscalYear.objects.filter(code=data["code"]).exists()
    if target == "periods":
        fy = _lookup(FiscalYear, text("fiscal_year"), "السنة المالية", normalizer)
        data = {"fiscal_year_id": fy.pk, "month": _integer(text("month"), "الشهر"),
                "start_date": _date(text("start_date"), "تاريخ البداية"), "end_date": _date(text("end_date"), "تاريخ النهاية"),
                "status": text("status", "open").lower(), "is_active": _boolean(text("is_active")), "notes": text("notes")}
        key = (fy.pk, data["month"])
        return MonthlyPeriod, data, key, MonthlyPeriod.objects.filter(fiscal_year=fy, month=data["month"]).exists()
    if target == "departments":
        parent = _lookup(Department, text("parent"), "الإدارة الأم", normalizer) if text("parent") else None
        data = {"code": text("code"), "name": text("name"), "parent_id": parent.pk if parent else None,
                "is_active": _boolean(text("is_active")), "notes": text("notes")}
        return Department, data, (data["code"],), Department.objects.filter(code=data["code"]).exists()
    if target == "expense_categories":
        data = {"code": text("code"), "name": text("name"), "description": text("description"),
                "is_active": _boolean(text("is_active"))}
        return ExpenseCategory, data, (data["code"],), ExpenseCategory.objects.filter(code=data["code"]).exists()
    if target == "accounts":
        data = _prepare_account(values)
        return Account, data, (data["code"],), False
    if target == "suppliers":
        data = {key: text(key) for key in ("code", "name", "contact_person", "phone", "email", "tax_number", "address", "notes")}
        data["is_active"] = _boolean(text("is_active"))
        return Supplier, data, (data["code"],), Supplier.objects.filter(code=data["code"]).exists()
    if target == "budget_lines":
        fy = _lookup(FiscalYear, text("fiscal_year"), "السنة المالية", normalizer)
        department = _lookup(Department, text("department"), "الإدارة", normalizer)
        account = _lookup(Account, text("account"), "الحساب", normalizer)
        if account.account_type != "expense":
            raise ValidationError("الحساب: سطور الموازنة تقبل حسابات المصروفات فقط.")
        if not account.is_operational:
            raise ValidationError("الحساب: يجب اختيار حساب نشط من المستوى الخامس.")
        category = _lookup(ExpenseCategory, text("expense_category"), "تصنيف المصروف", normalizer) if text("expense_category") else account.expense_category
        version = _integer(text("version"), "رقم النسخة", 1)
        budget_name = text("budget_name")
        months = {month: _decimal(text(month), month, allow_zero=True) for month in MONTH_FIELDS}
        existing_version = BudgetVersion.objects.filter(budget__fiscal_year=fy, version=version).first()
        if existing_version and existing_version.status == BudgetVersion.STATUS_APPROVED:
            raise ValidationError("نسخة الموازنة معتمدة ولا تقبل استيراد أسطر جديدة.")
        duplicate = BudgetLine.objects.filter(version__budget__fiscal_year=fy, version__version=version,
                                              department=department, account=account).exists()
        data = {"fiscal_year_id": fy.pk, "budget_name": budget_name, "version": version,
                "department_id": department.pk, "account_id": account.pk,
                "expense_category_id": category.pk if category else None, **months, "notes": text("notes")}
        return BudgetLine, data, (fy.pk, version, department.pk, account.pk), duplicate
    if target == "procurements":
        department = _lookup(Department, text("department"), "الإدارة", normalizer)
        supplier = _lookup(Supplier, text("supplier"), "المورد", normalizer)
        account = _lookup(Account, text("account"), "الحساب", normalizer)
        data = {"reference_number": text("reference_number"), "date": _date(text("date"), "التاريخ"),
                "department_id": department.pk, "supplier_id": supplier.pk, "account_id": account.pk,
                "expense_category_id": account.expense_category_id, "description": text("description"),
                "amount": _decimal(text("amount"), "المبلغ"), "status": text("status", "draft").lower(),
                "purchase_order": text("purchase_order"), "approval_reference": text("approval_reference"),
                "payment_method": text("payment_method", "transfer").lower(),
                "payment_reference": text("payment_reference"), "notes": text("notes")}
        key = (data["reference_number"],)
        return Procurement, data, key, Procurement.objects.filter(reference_number=data["reference_number"]).exists()
    procurement = Procurement.objects.filter(reference_number=text("procurement")).first()
    if not procurement:
        raise ValidationError(f"سجل المشتريات: «{text('procurement')}» غير موجود.")
    supplier = _lookup(Supplier, text("supplier"), "المورد", normalizer)
    data = {"procurement_id": procurement.pk, "supplier_id": supplier.pk,
            "amount": _decimal(text("amount"), "قيمة العرض"),
            "offer_date": _date(text("offer_date"), "تاريخ العرض") if text("offer_date") else None,
            "reference": text("reference"), "notes": text("notes")}
    key = (procurement.pk, supplier.pk)
    return Quotation, data, key, Quotation.objects.filter(procurement=procurement, supplier=supplier).exists()


def _validate_accounts_job(job):
    mapping = {key: source for key, source in (job.column_map or {}).items() if source}
    missing = [key for key in required_fields(job.target) if key not in mapping]
    if missing:
        labels = dict(target_fields(job.target))
        raise ValidationError("مطابقة الأعمدة غير مكتملة: " + "، ".join(labels[key] for key in missing))

    prepared = {}
    duplicate_codes = set()
    error_list = []
    for row in job.rows:
        mapped = {key: str(row["source"].get(source) or "").strip()
                  for key, source in mapping.items()}
        row["mapped"] = mapped
        try:
            ready = _prepare_account(mapped)
            if ready["code"] in prepared:
                duplicate_codes.add(ready["code"])
            else:
                prepared[ready["code"]] = (row, ready)
            row.update({"ready": _serialize(ready), "errors": [], "warnings": [],
                        "duplicate": False, "valid": True})
        except ValidationError as exc:
            row.update({"ready": {}, "errors": _errors(exc), "warnings": [],
                        "duplicate": False, "valid": False})

    database_accounts = {account.code: account for account in Account.objects.all()}
    for code, (row, ready) in prepared.items():
        errors = row["errors"]
        if code in duplicate_codes:
            errors.append("رقم الحساب مكرر داخل الملف.")
        level = ready["level"]
        parent_code = ready["parent_code"]
        expected_ledger = "sub" if level == 6 else "main"
        if ready["ledger_type"] != expected_ledger:
            errors.append("النوع لا يتوافق مع المستوى: 1–5 رئيسي، و6 فرعي.")
        if level == 1 and parent_code:
            errors.append("حساب المستوى الأول يجب ألا يحتوي حسابًا رئيسيًا.")
        if level > 1 and not parent_code:
            errors.append("الحساب الرئيسي مطلوب للمستويات من 2 إلى 6.")
        parent_ready = prepared.get(parent_code, (None, None))[1] if parent_code else None
        parent_db = database_accounts.get(parent_code) if parent_code else None
        if parent_code and not parent_ready and not parent_db:
            errors.append(f"الحساب الرئيسي «{parent_code}» غير موجود في الملف أو قاعدة البيانات.")
        parent_level = parent_ready["level"] if parent_ready else getattr(parent_db, "level", None)
        parent_type = parent_ready["account_type"] if parent_ready else getattr(parent_db, "account_type", None)
        if parent_code and parent_level is not None and parent_level != level - 1:
            errors.append("مستوى الحساب الرئيسي يجب أن يقل بدرجة واحدة عن مستوى الحساب.")
        if parent_code and parent_type and parent_type != ready["account_type"]:
            errors.append("نوع الحساب لا يتطابق مع نوع الحساب الرئيسي.")
        if code in database_accounts:
            row["warnings"].append("الحساب موجود وسيتم تحديث بياناته.")
        row["valid"] = not errors

    valid = invalid = error_count = warning_count = 0
    for row in job.rows:
        if row["valid"]:
            valid += 1
        else:
            invalid += 1
        for message in row["errors"]:
            error_count += 1
            if len(error_list) < 300:
                error_list.append({"row": row["index"], "message": message})
        warning_count += len(row["warnings"])
    job.summary = {"total": len(job.rows), "valid": valid, "invalid": invalid,
                   "duplicate": len(duplicate_codes), "errors": error_count,
                   "warnings": warning_count, "error_list": error_list,
                   "warning_list": []}
    job.status = ImportJob.STATUS_VALIDATED
    job.log("validation_completed", **{key: job.summary[key] for key in
            ("total", "valid", "invalid", "duplicate", "errors", "warnings")})
    job.save()
    return job.summary


def validate_locked_job(job, user, normalizer):
    if job.target == "accounts":
        return _validate_accounts_job(job)
    mapping = {key: source for key, source in (job.column_map or {}).items() if source}
    missing = [key for key in required_fields(job.target) if key not in mapping]
    if missing:
        labels = dict(target_fields(job.target))
        raise ValidationError("مطابقة الأعمدة غير مكتملة: " + "، ".join(labels[key] for key in missing))
    seen = {}
    error_list = []
    valid = invalid = duplicate_count = error_count = 0
    for row in job.rows:
        mapped = {key: str(row["source"].get(source) or "").strip() for key, source in mapping.items()}
        row["mapped"] = mapped
        errors = []
        duplicate = False
        ready = {}
        try:
            model, data, key, duplicate = _prepare(job.target, mapped, normalizer)
            if key in seen:
                duplicate = True
                errors.append(f"مكرر داخل الملف — يطابق الصف {seen[key]}.")
            elif duplicate:
                errors.append("مكرر في قاعدة البيانات.")
            else:
                if model is not BudgetLine:
                    instance = model(**data)
                    instance.full_clean()
            seen.setdefault(key, row["index"])
            ready = _serialize(data)
        except ValidationError as exc:
            errors.extend(_errors(exc))
        row.update({"ready": ready, "errors": errors, "warnings": [],
                    "duplicate": duplicate, "valid": not errors and not duplicate})
        if row["valid"]:
            valid += 1
        elif duplicate:
            duplicate_count += 1
        else:
            invalid += 1
        for message in errors:
            error_count += 1
            if len(error_list) < 300:
                error_list.append({"row": row["index"], "message": message})
    job.summary = {"total": len(job.rows), "valid": valid, "invalid": invalid,
                   "duplicate": duplicate_count, "errors": error_count, "warnings": 0,
                   "error_list": error_list, "warning_list": []}
    job.status = ImportJob.STATUS_VALIDATED
    job.log("validation_completed", **{key: job.summary[key] for key in
            ("total", "valid", "invalid", "duplicate", "errors", "warnings")})
    job.save()
    return job.summary


def _deserialize(target, ready):
    data = dict(ready)
    date_fields = {"fiscal_years": ("start_date", "end_date"), "periods": ("start_date", "end_date"),
                   "procurements": ("date",), "quotations": ("offer_date",)}.get(target, ())
    decimal_fields = MONTH_FIELDS if target == "budget_lines" else (("amount",) if target in {"procurements", "quotations"} else ())
    for field in date_fields:
        if data.get(field):
            data[field] = date.fromisoformat(data[field])
    for field in decimal_fields:
        if data.get(field) is not None:
            data[field] = Decimal(data[field])
    return data


def run_locked_job(job, user, request=None):
    rows = [row for row in job.rows if row.get("valid")]
    if not rows:
        raise ValidationError("لا توجد صفوف صالحة للاستيراد.")
    model_map = {"fiscal_years": FiscalYear, "periods": MonthlyPeriod, "departments": Department,
                 "expense_categories": ExpenseCategory, "accounts": Account, "suppliers": Supplier,
                 "procurements": Procurement, "quotations": Quotation}
    imported = 0
    if job.target == "accounts":
        rows.sort(key=lambda row: (int(row["ready"]["level"]), row["index"]))
    for row in rows:
        data = _deserialize(job.target, row["ready"])
        if job.target == "accounts":
            parent_code = data.pop("parent_code", "")
            data["parent_id"] = (Account.objects.only("pk").get(code=parent_code).pk
                                 if parent_code else None)
            instance = Account.objects.filter(code=data["code"]).first() or Account(code=data["code"])
            for field, value in data.items():
                setattr(instance, field, value)
        elif job.target == "budget_lines":
            fy = FiscalYear.objects.get(pk=data.pop("fiscal_year_id"))
            budget_name = data.pop("budget_name")
            version_number = data.pop("version")
            budget, _ = Budget.objects.get_or_create(fiscal_year=fy, defaults={"name": budget_name, "created_by": user, "updated_by": user})
            version, _ = BudgetVersion.objects.get_or_create(budget=budget, version=version_number,
                                                              defaults={"status": BudgetVersion.STATUS_DRAFT, "created_by": user, "updated_by": user})
            if version.status == BudgetVersion.STATUS_APPROVED:
                raise ValidationError("تغيرت حالة نسخة الموازنة إلى معتمدة؛ أُوقف الاستيراد.")
            instance = BudgetLine(version=version, **data)
        else:
            instance = model_map[job.target](**data)
        if hasattr(instance, "created_by_id"):
            instance.created_by = user
        if hasattr(instance, "updated_by_id"):
            instance.updated_by = user
        if isinstance(instance, Procurement) and instance.approval_reference:
            instance.approved_by = user
            instance.approved_at = timezone.now()
        instance.full_clean()
        instance.save()
        imported += 1
    job.status = ImportJob.STATUS_COMPLETED
    job.imported_count = imported
    job.log("import_completed", imported=imported, skipped=len(job.rows) - imported)
    job.save()
    log_action(action="data_imported", entity_type="import_job", entity_id=job.pk,
               diff={"target": job.target, "file": job.original_filename, "imported": imported,
                     "skipped": len(job.rows) - imported,
                     "summary": {key: job.summary.get(key) for key in ("total", "valid", "invalid", "duplicate")}},
               request=request, actor=user)
    return imported
