"""PHASE 12 — عرض التقارير التسعة + تصدير CSV/XLSX (من نفس البناء الحي)."""
import csv
import io
from datetime import datetime

from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render

from apps.accounts.permissions import require_permission
from apps.governance.services import log_action
from apps.reports.builders import REPORTS, parse_filters, resolve_window

FILTER_LABELS = {
    "period": "الفترة",
    "department": "الإدارة",
    "account": "الحساب",
    "category": "التصنيف",
    "risk": "Risk",
    "test": "الاختبار",
}


def _options():
    from apps.audit_register.models import AuditTest
    from apps.reference.models import (
        Account,
        Department,
        ExpenseCategory,
        MonthlyPeriod,
    )
    months_ar = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                 "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    return {
        "departments": list(Department.objects.order_by("name").values(
            "id", "name")),
        "accounts": list(Account.objects.order_by("code").values(
            "id", "code", "name")),
        "categories": list(ExpenseCategory.objects.order_by("name").values(
            "id", "name")),
        "periods": [
            {"id": p.id,
             "label": f"{months_ar[p.month - 1]} {p.fiscal_year.code}"}
            for p in MonthlyPeriod.objects.select_related(
                "fiscal_year").order_by("fiscal_year__year", "month")
        ],
        "risks": ["High", "Medium", "Low"],
        "tests": list(AuditTest.objects.order_by("test_code").values(
            "test_code", "name")),
    }


def _build(slug: str, request):
    meta = REPORTS[slug]  # callers validate slug against REPORTS first
    filters = parse_filters(request)
    window = resolve_window(filters)
    columns, rows, summary = meta["builder"](filters, window)
    active = [
        {"label": FILTER_LABELS[k], "value": _filter_display(k, filters[k])}
        for k in meta["filters"] if filters.get(k)
    ]
    return meta, filters, window, columns, rows, summary, active


def _filter_display(kind, value):
    if kind == "period":
        from apps.reference.models import MonthlyPeriod
        months_ar = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                     "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر",
                     "ديسمبر"]
        p = MonthlyPeriod.objects.select_related("fiscal_year").filter(
            pk=value).first()
        if p:
            return f"{months_ar[p.month - 1]} {p.fiscal_year.code}"
        return str(value)
    if kind == "department":
        from apps.reference.models import Department
        obj = Department.objects.filter(pk=value).first()
        return obj.name if obj else str(value)
    if kind == "account":
        from apps.reference.models import Account
        obj = Account.objects.filter(pk=value).first()
        return f"{obj.code} — {obj.name}" if obj else str(value)
    if kind == "category":
        from apps.reference.models import ExpenseCategory
        obj = ExpenseCategory.objects.filter(pk=value).first()
        return obj.name if obj else str(value)
    if kind == "test":
        return value
    return str(value)


@require_permission("reports.view")
def report_list(request):
    return render(request, "reports/list.html", {
        "reports": [
            {"slug": slug, **meta} for slug, meta in REPORTS.items()
        ],
    })


@require_permission("reports.view")
def report_detail(request, slug):
    if slug not in REPORTS:
        return HttpResponseBadRequest("تقرير غير معروف.")
    meta, filters, window, columns, rows, summary, active = _build(
        slug, request)
    return render(request, "reports/report.html", {
        "report": {"slug": slug, "title": meta["title"],
                   "title_ar": meta["title_ar"],
                   "description": meta["description"]},
        "allowed_filters": meta["filters"],
        "filter_options": _options(),
        "filters": filters,
        "active_filters": active,
        "window": {"from": window[1], "to": window[2]},
        "columns": columns,
        "rows": rows,
        "summary": summary,
        "row_count": len(rows),
        "generated_at": datetime.now(),
    })


def _cell_value(cell):
    value = cell.get("v", "")
    return value


@require_permission("reports.generate")
def report_export(request, slug, fmt):
    if slug not in REPORTS:
        return HttpResponseBadRequest("تقرير غير معروف.")
    if fmt not in ("csv", "xlsx"):
        return HttpResponseBadRequest("صيغة غير مدعومة.")
    meta, filters, window, columns, rows, summary, active = _build(
        slug, request)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"{slug}-{stamp}.{fmt}"

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([c["label"] for c in columns])
        for row in rows:
            writer.writerow([_cell_value(row[c["key"]])
                             for c in columns])
        writer.writerow([])
        writer.writerow(["الملخص"])
        for item in summary:
            writer.writerow([item["label"], item["value"]])
        data = buf.getvalue().encode("utf-8-sig")  # BOM لفتح Excel بالعربية
        response = HttpResponse(data, content_type="text/csv; charset=utf-8")
    else:
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = meta["title"][:31]
        ws.append([c["label"] for c in columns])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([_cell_value(row[c["key"]]) for c in columns])
        ws.append([])
        ws.append(["الملخص"])
        for item in summary:
            ws.append([item["label"], item["value"]])
        out = io.BytesIO()
        wb.save(out)
        response = HttpResponse(
            out.getvalue(),
            content_type=("application/vnd.openxmlformats-officedocument"
                          ".spreadsheetml.sheet"))
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"')
    log_action(
        action="report_exported",
        entity_type="report",
        entity_id=slug,
        diff={"format": fmt, "rows": len(rows),
              "filters": {k: v for k, v in filters.items() if v}},
        request=request,
    )
    return response
