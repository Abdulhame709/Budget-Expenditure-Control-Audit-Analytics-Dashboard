"""PHASE 4 — generic, registry-driven CRUD for the six reference modules.

Every module is described once in REFERENCE_MODULES; the four views
(list / create / edit / delete) + detail are shared. Enforcement:

- page-level  : AccessControlMiddleware via URL_PERMISSIONS (direct URLs)
- action-level: @require_permission on every mutating view
- audit trail : entity_created / entity_updated / entity_deleted /
                period_status_changed — via reference.services
- closed periods: status changes ONLY through period_set_status (audited);
  transaction posting is guarded by services.require_period_postable.
"""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounts.permissions import has_perm, require_permission
from apps.governance.models import AuditLog

from . import forms
from .models import (
    Account,
    Currency,
    Department,
    Employee,
    ExpenseCategory,
    FiscalYear,
    MonthlyPeriod,
    OrganizationSettings,
    Supplier,
)
from .services import changes_between, log_reference_action, snapshot

# ---------------------------------------------------------------- registry
REFERENCE_MODULES: dict[str, dict] = {
    "currency": {
        "model": Currency,
        "form": forms.CurrencyForm,
        "path": "currencies",
        "title": "العملات",
        "title_one": "عملة",
        "columns": [
            ("code", "الرمز"), ("name_ar", "الاسم"), ("symbol", "الشعار"),
            ("exchange_rate_to_base", "سعر التحويل"),
            ("is_base", "أساسية"), ("is_active", "الحالة"),
        ],
        "detail_fields": [
            "code", "name_ar", "name_en", "symbol", "decimal_places",
            "exchange_rate_to_base", "is_base", "is_active",
        ],
        "search": ["code", "name_ar", "name_en"],
        "filters": {"status": "is_active"},
        "filter_specs": [
            ("status", "الحالة", [("", "الكل"), ("active", "نشط"), ("inactive", "معطّل")]),
        ],
        "paginate_by": 15,
    },
    "fiscal_year": {
        "model": FiscalYear,
        "form": forms.FiscalYearForm,
        "path": "fiscal-years",
        "title": "السنوات المالية",
        "title_one": "سنة مالية",
        "columns": [
            ("code", "الرمز"), ("name", "الاسم"), ("year", "السنة"),
            ("start_date", "من"), ("end_date", "إلى"), ("is_active", "الحالة"),
        ],
        "detail_fields": [
            "code", "name", "year", "start_date", "end_date", "is_active", "notes",
        ],
        "search": ["code", "name"],
        "search_int": "year",
        "filters": {"status": "is_active"},
        "filter_specs": [
            ("status", "الحالة", [("", "الكل"), ("active", "نشط"), ("inactive", "معطّل")]),
        ],
        "paginate_by": 15,
    },
    "period": {
        "model": MonthlyPeriod,
        "form": forms.MonthlyPeriodForm,
        "path": "periods",
        "title": "الفترات الشهرية",
        "title_one": "فترة شهرية",
        "columns": [
            ("fiscal_year", "السنة المالية"), ("month", "الشهر"),
            ("start_date", "من"), ("end_date", "إلى"),
            ("status", "الحالة"), ("is_active", "نشط/معطّل"),
        ],
        "detail_fields": [
            "fiscal_year", "month", "start_date", "end_date", "status",
            "is_active", "notes",
        ],
        "search": ["fiscal_year__code", "fiscal_year__name", "notes"],
        "filters": {"status": "is_active", "pstatus": "status", "fy": "fiscal_year"},
        "fk_filters": ["fy"],
        "filter_specs": [
            ("status", "الحالة", [("", "الكل"), ("active", "نشط"), ("inactive", "معطّل")]),
            ("pstatus", "الفتح/الإغلاق", [("", "الكل"), ("open", "مفتوحة"), ("closed", "مغلقة")]),
        ],
        "paginate_by": 15,
    },
    "department": {
        "model": Department,
        "form": forms.DepartmentForm,
        "path": "departments",
        "title": "الإدارات",
        "title_one": "إدارة",
        "columns": [
            ("code", "الرمز"), ("name", "الاسم"), ("parent", "الإدارة الأب"),
            ("is_active", "الحالة"),
        ],
        "detail_fields": ["code", "name", "parent", "is_active", "notes"],
        "search": ["code", "name"],
        "filters": {"status": "is_active"},
        "filter_specs": [
            ("status", "الحالة", [("", "الكل"), ("active", "نشط"), ("inactive", "معطّل")]),
        ],
        "paginate_by": 15,
    },
    "employee": {
        "model": Employee,
        "form": forms.EmployeeForm,
        "path": "employees",
        "title": "الموظفون",
        "title_one": "موظف",
        "columns": [
            ("code", "رقم الموظف"), ("full_name", "الاسم"),
            ("department", "الإدارة"), ("job_title", "المسمى الوظيفي"),
            ("contract_type", "نوع التعاقد"), ("is_active", "الحالة"),
        ],
        "detail_fields": [
            "code", "full_name", "department", "cost_center", "job_title",
            "contract_type", "start_date", "end_date", "is_active", "notes",
        ],
        "search": ["code", "full_name", "job_title", "cost_center", "department__name"],
        "filters": {
            "status": "is_active", "contract": "contract_type",
            "department": "department",
        },
        "fk_filters": ["department"],
        "filter_specs": [
            ("status", "الحالة", [("", "الكل"), ("active", "نشط"), ("inactive", "معطّل")]),
            ("contract", "نوع التعاقد", [("", "الكل"), *Employee.CONTRACT_TYPE_CHOICES]),
        ],
        "fk_filter_specs": [("department", "الإدارة", Department)],
        "paginate_by": 20,
    },
    "account": {
        "model": Account,
        "form": forms.AccountForm,
        "path": "accounts",
        "title": "دليل الحسابات",
        "title_one": "حساب",
        "columns": [
            ("code", "رقم الحساب"), ("name", "الاسم"), ("account_type", "النوع"),
            ("parent", "الحساب الأب"), ("expense_category", "تصنيف المصروف"),
            ("is_active", "الحالة"),
        ],
        "detail_fields": [
            "code", "name", "account_type", "parent", "expense_category",
            "is_active", "notes",
        ],
        "search": ["code", "name"],
        "filters": {"status": "is_active", "type": "account_type",
                    "category": "expense_category"},
        "fk_filters": ["category"],
        "filter_specs": [
            ("status", "الحالة", [("", "الكل"), ("active", "نشط"), ("inactive", "معطّل")]),
            ("type", "النوع", [("", "الكل"), ("expense", "مصروفات"),
                               ("asset", "أصول"), ("liability", "التزامات"),
                               ("equity", "حقوق ملكية"), ("income", "إيرادات")]),
        ],
        "paginate_by": 20,
    },
    "expense_category": {
        "model": ExpenseCategory,
        "form": forms.ExpenseCategoryForm,
        "path": "expense-categories",
        "title": "تصنيفات المصروفات",
        "title_one": "تصنيف مصروفات",
        "columns": [("code", "الرمز"), ("name", "الاسم"), ("is_active", "الحالة")],
        "detail_fields": ["code", "name", "description", "is_active"],
        "search": ["code", "name"],
        "filters": {"status": "is_active"},
        "filter_specs": [
            ("status", "الحالة", [("", "الكل"), ("active", "نشط"), ("inactive", "معطّل")]),
        ],
        "paginate_by": 15,
    },
    "supplier": {
        "model": Supplier,
        "form": forms.SupplierForm,
        "path": "suppliers",
        "title": "الموردون",
        "title_one": "مورّد",
        "columns": [
            ("code", "الرمز"), ("name", "الاسم"), ("phone", "الهاتف"),
            ("email", "البريد"), ("tax_number", "الرقم الضريبي"),
            ("is_active", "الحالة"),
        ],
        "detail_fields": [
            "code", "name", "contact_person", "phone", "email", "tax_number",
            "address", "is_active", "notes",
        ],
        "search": ["code", "name", "contact_person", "tax_number"],
        "filters": {"status": "is_active"},
        "filter_specs": [
            ("status", "الحالة", [("", "الكل"), ("active", "نشط"), ("inactive", "معطّل")]),
        ],
        "paginate_by": 15,
    },
}


def _cfg(slug: str) -> dict:
    try:
        return REFERENCE_MODULES[slug]
    except KeyError:
        raise PermissionDenied("وحدة غير معروفة.")


@require_permission("settings.manage")
def organization_settings(request):
    instance = OrganizationSettings.load()
    if instance is None and not Currency.objects.filter(is_base=True).exists():
        messages.error(
            request,
            "يجب تهيئة العملة الأساسية أولًا قبل إعداد بيانات المنشأة.",
        )
        return redirect("reference:currency_list")

    before = snapshot(instance) if instance else {}
    if request.method == "POST":
        form = forms.OrganizationSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            settings_obj = form.save(commit=False)
            if not settings_obj.pk:
                settings_obj.created_by = request.user
            settings_obj.updated_by = request.user
            settings_obj.save()
            action = "entity_updated" if instance else "entity_created"
            diff = changes_between(settings_obj, before) if instance else snapshot(settings_obj)
            log_reference_action(action, settings_obj, diff, request)
            messages.success(request, "تم حفظ إعدادات المنشأة والنظام.")
            return redirect("reference:organization_settings")
    else:
        initial = {}
        if instance is None:
            initial["base_currency"] = Currency.objects.filter(is_base=True).first()
        form = forms.OrganizationSettingsForm(instance=instance, initial=initial)
    return render(request, "reference/organization_settings.html", {
        "form": form,
        "settings_obj": instance,
    })


# ---------------------------------------------------------------- helpers
def _display(obj, attr: str):
    """Human display value: choices → Arabic label, FK → __str__, empty → —."""
    parts = attr.split("__")
    cur = obj
    for p in parts[:-1]:
        cur = getattr(cur, p, None)
        if cur is None:
            return "—"
    last = parts[-1]
    if hasattr(cur, "_meta"):
        try:
            field = cur._meta.get_field(last)
        except Exception:
            field = None
        if field is not None and field.choices:
            return getattr(cur, f"get_{last}_display")()
    value = getattr(cur, last, None)
    if hasattr(value, "pk"):  # FK
        return str(value) if value.pk else "—"
    if last == "is_active":
        return "نشط" if value else "معطّل"
    if value in (None, ""):
        return "—"
    if hasattr(value, "isoformat"):
        return value.strftime("%Y-%m-%d") if not isinstance(value, str) else value
    return value


def _apply_filters(qs, cfg: dict, get):
    fk_params = set(cfg.get("fk_filters", []))
    for param, field in cfg.get("filters", {}).items():
        raw = (get.get(param) or "").strip()
        if not raw:
            continue
        if field == "is_active":
            if raw in ("active", "inactive"):
                qs = qs.filter(is_active=(raw == "active"))
        elif field == "status":
            valid = {c[0] for c in MonthlyPeriod.STATUS_CHOICES}
            if raw in valid:
                qs = qs.filter(status=raw)
        elif param in fk_params:
            if raw.isdigit():          # FK filter — real pk only
                qs = qs.filter(**{field: int(raw)})
        else:                          # exact choice value (e.g. account_type)
            qs = qs.filter(**{field: raw})
    return qs


def _apply_search(qs, cfg: dict, q: str):
    if not q:
        return qs
    cond = Q()
    for f in cfg.get("search", []):
        cond |= Q(**{f"{f}__icontains": q})
    if q.isdigit() and cfg.get("search_int"):
        cond |= Q(**{f"{cfg['search_int']}": int(q)})
    return qs.filter(cond) if cond else qs


def _cell_rows(page, cfg) -> list[dict]:
    rows = []
    for obj in page:
        cells = []
        for attr, label in cfg["columns"]:
            value = _display(obj, attr)
            badge = None
            if attr == "is_active":
                badge = "success" if value == "نشط" else "danger"
            elif attr == "status":
                badge = "success" if value == "مفتوحة" else "danger"
            cells.append({"label": label, "value": value, "badge": badge})
        rows.append({
            "obj": obj, "cells": cells,
            "detail_url": reverse(f"reference:{cfg['name']}_detail", args=[obj.pk]),
            "edit_url": reverse(f"reference:{cfg['name']}_edit", args=[obj.pk]),
            "delete_url": reverse(f"reference:{cfg['name']}_delete", args=[obj.pk]),
        })
    return rows


def _urls_for(slug: str, cfg: dict) -> dict:
    cfg = dict(cfg)
    cfg["name"] = slug
    cfg["create_url"] = reverse(f"reference:{slug}_create")
    cfg["list_url"] = reverse(f"reference:{slug}_list")
    return cfg


# ---------------------------------------------------------------- views
def module_list(request, slug):
    cfg = _urls_for(slug, _cfg(slug))
    qs = cfg["model"].objects.all()
    q = (request.GET.get("q") or "").strip()
    qs = _apply_search(qs, cfg, q)
    qs = _apply_filters(qs, cfg, request.GET)

    paginator = Paginator(qs, cfg.get("paginate_by", 15))
    page_no = request.GET.get("page")
    try:
        page = paginator.get_page(page_no)
    except PageNotAnInteger:
        page = paginator.get_page(1)
    except EmptyPage:
        page = paginator.get_page(paginator.num_pages)

    filter_specs = list(cfg["filter_specs"])
    for param, label, model in cfg.get("fk_filter_specs", []):
        options = [("", "الكل")]
        options.extend((str(obj.pk), str(obj)) for obj in model.objects.order_by("code"))
        filter_specs.append((param, label, options))

    # active filter values for re-rendering the selects
    active_filters = {
        param: (request.GET.get(param) or "")
        for param, _, _ in filter_specs
    }
    context = {
        **cfg,
        "filter_specs": filter_specs,
        "q": q,
        "rows": _cell_rows(page, cfg),
        "page_obj": page,
        "total": paginator.count,
        "active_filters": active_filters,
        "can_edit": has_perm(request.user, "reference.edit"),
    }
    return render(request, "reference/module_list.html", context)


@require_permission("reference.edit")
def module_create(request, slug):
    cfg = _urls_for(slug, _cfg(slug))
    if request.method == "POST":
        form = cfg["form"](request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.updated_by = request.user
            obj.save()
            log_reference_action("entity_created", obj, snapshot(obj), request)
            messages.success(
                request, f"تم إنشاء {cfg['title_one']} «{obj}» وتسجيله في سجل التدقيق."
            )
            return redirect("reference:%s_detail" % slug, pk=obj.pk)
    else:
        form = cfg["form"]()
    return render(request, "reference/module_form.html", {
        **cfg, "form": form, "is_create": True,
    })


def module_detail(request, slug, pk):
    cfg = _urls_for(slug, _cfg(slug))
    obj = get_object_or_404(cfg["model"], pk=pk)
    field_rows = [
        {"label": cfg["model"]._meta.get_field(name).verbose_name,
         "value": _display(obj, name)}
        for name in cfg["detail_fields"]
    ]
    audit_rows = []
    if has_perm(request.user, "audittrail.view"):
        audit_rows = AuditLog.objects.filter(
            entity_type=cfg["model"]._meta.model_name, entity_id=str(obj.pk)
        )[:10]
    return render(request, "reference/module_detail.html", {
        **cfg, "obj": obj, "field_rows": field_rows, "audit_rows": audit_rows,
        "can_edit": has_perm(request.user, "reference.edit"),
        "can_trail": has_perm(request.user, "audittrail.view"),
        "edit_url": reverse(f"reference:{slug}_edit", args=[obj.pk]),
        "delete_url": reverse(f"reference:{slug}_delete", args=[obj.pk]),
        "set_status_url": reverse("reference:period_set_status", args=[obj.pk])
        if slug == "period" else "",
    })


@require_permission("reference.edit")
def module_edit(request, slug, pk):
    cfg = _urls_for(slug, _cfg(slug))
    obj = get_object_or_404(cfg["model"], pk=pk)
    before = snapshot(obj)
    if request.method == "POST":
        form = cfg["form"](request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            diff = changes_between(obj, before)
            if diff:
                log_reference_action("entity_updated", obj, diff, request)
                messages.success(
                    request, f"تم تعديل {cfg['title_one']} «{obj}» وتسجيل الفروق في سجل التدقيق."
                )
            else:
                messages.info(request, "لا توجد تغييرات لحفظها.")
            return redirect("reference:%s_detail" % slug, pk=obj.pk)
    else:
        form = cfg["form"](instance=obj)
    return render(request, "reference/module_form.html", {
        **cfg, "form": form, "is_create": False, "obj": obj,
    })


@require_permission("reference.edit")
def module_delete(request, slug, pk):
    """DELETE (POST only): allowed only when nothing references the row;
    otherwise ProtectedError → instruct to deactivate instead (audit-safe)."""
    cfg = _urls_for(slug, _cfg(slug))
    obj = get_object_or_404(cfg["model"], pk=pk)
    if request.method != "POST":
        messages.error(request, "الحذف يتطلب تأكيدًا (POST).")
        return redirect("reference:%s_detail" % slug, pk=obj.pk)
    before = snapshot(obj)
    label = str(obj)
    row_pk, model_name = obj.pk, obj._meta.model_name
    try:
        obj.delete()
    except ProtectedError:
        messages.error(
            request,
            f"لا يمكن حذف «{label}» لارتباطه بسجلات أخرى — استخدم التعطيل "
            "(نشط/معطّل) للحفاظ على السلامة المرجعية.",
        )
        return redirect("reference:%s_detail" % slug, pk=row_pk)
    log_reference_action(
        "entity_deleted",
        _DeletedProxy(model_name, row_pk),
        {"snapshot": before, "label": label},
        request,
    )
    messages.success(request, f"تم حذف {cfg['title_one']} «{label}» وتسجيله في سجل التدقيق.")
    return redirect(cfg["list_url"])


class _DeletedProxy:
    """Minimal stand-in so log_reference_action can read model_name/pk
    after the row is gone."""

    def __init__(self, model_name: str, pk):
        self._meta = type("M", (), {"model_name": model_name})()
        self.pk = pk


@require_permission("reference.edit")
def period_set_status(request, pk):
    """The ONLY way to open/close a period — always lands in the Audit Trail."""
    if request.method != "POST":
        messages.error(request, "الإجراء يتطلب POST.")
        return redirect("reference:period_detail", pk=pk)
    period = get_object_or_404(MonthlyPeriod, pk=pk)
    target = (request.POST.get("status") or "").strip()
    valid = {c[0] for c in MonthlyPeriod.STATUS_CHOICES}
    if target not in valid:
        messages.error(request, "قيمة الحالة غير صحيحة.")
        return redirect("reference:period_detail", pk=pk)
    if target == period.status:
        messages.info(request, "الحالة لم تتغير.")
        return redirect("reference:period_detail", pk=pk)
    before = period.status
    period.status = target
    period.updated_by = request.user
    period.save(update_fields=["status", "updated_by", "updated_at"])
    log_reference_action(
        "period_status_changed", period,
        {"before": before, "after": target, "period": str(period)},
        request,
    )
    verb = "إغلاق" if target == MonthlyPeriod.STATUS_CLOSED else "فتح"
    messages.success(
        request,
        f"تم {verb} الفترة «{period}» وتسجيل العملية في سجل التدقيق."
        + ("" if target == MonthlyPeriod.STATUS_OPEN else
           " التسجيل في هذه الفترة يتطلب الآن صلاحية «التسجيل في فترة مغلقة».")
    )
    return redirect("reference:period_detail", pk=pk)
