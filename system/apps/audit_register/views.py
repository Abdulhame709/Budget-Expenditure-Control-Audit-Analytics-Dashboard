"""PHASE 9 — Audit Test Engine views.

Tests CRUD/enable-disable (audit.rules.manage) · run single/selected/all
(audit.run) · run + results + exceptions viewing (audit.view) · exception
handling (exceptions.view / exceptions.manage) — all existing catalog codes.
"""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import require_permission
from apps.audit_register.forms import (
    AuditTestForm,
    EvidenceUploadForm,
    FindingForm,
)
from apps.audit_register.models import (
    AuditException,
    AuditFinding,
    AuditRun,
    AuditTest,
    AuditTestResult,
)
from apps.audit_register import services as engine
from apps.governance.services import log_action


# ---------------------------------------------------------------- tests
@require_permission("audit.view")
def tests_list(request):
    from apps.accounts.permissions import has_perm
    tests = AuditTest.objects.all()
    last_run = AuditRun.objects.order_by("-started_at").first()
    return render(request, "audit/tests_list.html", {
        "tests": tests,
        "last_run": last_run,
        "active_count": tests.filter(is_active=True).count(),
        "can_manage": has_perm(request.user, "audit.rules.manage"),
        "engine_choices": engine.ENGINE_CHOICES,
    })


@require_permission("audit.rules.manage")
def test_create(request):
    form = AuditTestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        test = form.save(commit=False)
        test.parameters = form.cleaned_data["parameters_json"]
        test.created_by = request.user
        test.updated_by = request.user
        test.save()
        log_action(action="entity_created", entity_type="audit_test",
                   entity_id=test.pk,
                   diff={"test_code": test.test_code, "name": test.name,
                         "engine_key": test.engine_key},
                   request=request)
        messages.success(
            request, f"أُنشئ الاختبار {test.test_code} — مفعّل وجدول "
                     f"التشغيل.")
        return redirect("audit:tests_list")
    return render(request, "audit/test_form.html",
                  {"form": form, "creating": True})


@require_permission("audit.rules.manage")
def test_edit(request, pk):
    test = get_object_or_404(AuditTest, pk=pk)
    # لقطة قبل أي معالجة: ModelForm.is_valid() يعدّل الـ instance في _post_clean
    before = {
        "is_active": test.is_active,
        "engine_key": test.engine_key,
        "parameters": test.parameters,
        "rule_text": test.rule_text,          # Change Rule traceability
        "default_risk": test.default_risk,    # Change Risk traceability
        "auditor_action": test.auditor_action,
    }
    form = AuditTestForm(request.POST or None, instance=test)
    if request.method == "POST" and form.is_valid():
        test = form.save(commit=False)
        test.parameters = form.cleaned_data["parameters_json"]
        test.updated_by = request.user
        test.save()
        log_action(action="entity_updated", entity_type="audit_test",
                   entity_id=test.pk,
                   diff={"test_code": test.test_code,
                         "before": before,
                         "after": {"is_active": test.is_active,
                                   "engine_key": test.engine_key,
                                   "parameters": test.parameters,
                                   "rule_text": test.rule_text,
                                   "default_risk": test.default_risk,
                                   "auditor_action": test.auditor_action}},
                   request=request)
        messages.success(request, f"حُفظ تعديلات {test.test_code}.")
        return redirect("audit:tests_list")
    return render(request, "audit/test_form.html",
                  {"form": form, "creating": False, "test": test})


@require_permission("audit.rules.manage")
@require_POST
def test_toggle(request, pk):
    test = get_object_or_404(AuditTest, pk=pk)
    test.is_active = not test.is_active
    test.updated_by = request.user
    test.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_action(action="entity_updated", entity_type="audit_test",
               entity_id=test.pk,
               diff={"test_code": test.test_code,
                     "is_active": test.is_active},
               request=request)
    messages.info(
        request,
        f"{'فُعّل' if test.is_active else 'أُعطّل'} الاختبار "
        f"{test.test_code}.")
    return redirect("audit:tests_list")


# ---------------------------------------------------------------- runs
@require_permission("audit.run")
@require_POST
def run_start(request):
    mode = request.POST.get("mode") or AuditRun.MODE_ALL
    test_ids = request.POST.getlist("test_ids")
    try:
        tests, _ = engine.resolve_tests(mode=mode, test_ids=test_ids)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("audit:tests_list")
    run = engine.start_run(tests, request.user, mode=mode, request=request)
    messages.success(
        request,
        f"اكتمل تشغيل {run.run_number}: {run.tests_pass} pass · "
        f"{run.tests_flagged} flagged · {run.tests_fail} fail · "
        f"{run.exceptions_total} استثناء.")
    return redirect("audit:run_detail", run.pk)


@require_permission("audit.view")
def runs_list(request):
    runs = AuditRun.objects.select_related("triggered_by")[:100]
    return render(request, "audit/runs_list.html", {"runs": runs})


@require_permission("audit.view")
def run_detail(request, pk):
    run = get_object_or_404(
        AuditRun.objects.select_related("triggered_by"), pk=pk)
    results = run.results.select_related("test")
    exceptions = run.exceptions.select_related(
        "test", "handled_by").order_by(
        "status", "-risk_level", "-amount")
    return render(request, "audit/run_detail.html", {
        "run": run, "results": results, "exceptions": exceptions,
    })


# ---------------------------------------------------------------- exceptions
@require_permission("exceptions.view")
def exceptions_list(request):
    qs = AuditException.objects.select_related("test", "run", "handled_by")
    sel = {
        "status": request.GET.get("status", ""),
        "risk": request.GET.get("risk", ""),
        "test_code": request.GET.get("test_code", ""),
        "run": request.GET.get("run", ""),
        "q": request.GET.get("q", "").strip(),
    }
    if sel["status"]:
        qs = qs.filter(status=sel["status"])
    if sel["risk"]:
        qs = qs.filter(risk_level=sel["risk"])
    if sel["test_code"]:
        qs = qs.filter(test_code=sel["test_code"])
    if sel["run"]:
        qs = qs.filter(run__run_number=sel["run"])
    if sel["q"]:
        from django.db.models import Q
        qs = qs.filter(
            Q(explanation__icontains=sel["q"])
            | Q(source_id__icontains=sel["q"])
            | Q(title__icontains=sel["q"]))
    counts = {
        "open": AuditException.objects.filter(status="open").count(),
        "acknowledged": AuditException.objects.filter(
            status="acknowledged").count(),
        "resolved": AuditException.objects.filter(status="resolved").count(),
        "high": AuditException.objects.filter(risk_level="High").count(),
        "total": AuditException.objects.count(),
    }
    from apps.accounts.permissions import has_perm
    return render(request, "audit/exceptions_list.html", {
        "exceptions": qs[:300], "sel": sel, "counts": counts,
        "can_manage": has_perm(request.user, "exceptions.manage"),
        "test_codes": AuditTest.objects.values_list("test_code", flat=True),
    })


@require_permission("exceptions.manage")
@require_POST
def exception_update(request, pk):
    exc = get_object_or_404(AuditException, pk=pk)
    status = request.POST.get("status")
    note = (request.POST.get("status_note") or "").strip()
    if status not in dict(AuditException.STATUS_CHOICES):
        messages.error(request, "حالة غير صالحة.")
        return redirect("audit:exceptions_list")
    before = exc.status
    exc.status = status
    exc.status_note = note
    if status != AuditException.STATUS_OPEN:
        exc.handled_by = request.user
        exc.handled_at = timezone.now()
    else:
        exc.handled_by = None
        exc.handled_at = None
    exc.save()
    log_action(action="entity_updated", entity_type="audit_exception",
               entity_id=exc.pk,
               diff={"test_code": exc.test_code,
                     "source": f"{exc.source_type}#{exc.source_id}",
                     "status": {"before": before, "after": status},
                     "note": note[:200]},
               request=request)
    messages.success(request, f"حُدِّثت حالة الاستثناء إلى "
                              f"«{exc.get_status_display()}».")
    return redirect(request.META.get("HTTP_REFERER")
                    or "audit:exceptions_list")


# ================================================================ PHASE 10
# Audit cycle: Dashboard(hub) → Exception → Source → Test → Finding
# The hub is a MINIMAL cycle landing page (navigation start point) — the full
# DB dashboard module remains a later, separately-ordered phase.

@require_permission("audit.view")
def cycle_hub(request):
    exc_qs = AuditException.objects.all()
    find_qs = AuditFinding.objects.all()
    from django.db.models import Count
    ctx = {
        "exc_by_status": dict(
            exc_qs.values_list("status").annotate(n=Count("id"))),
        "exc_by_risk": dict(
            exc_qs.values_list("risk_level").annotate(n=Count("id"))),
        "exc_total": exc_qs.count(),
        "find_by_status": dict(
            find_qs.values_list("status").annotate(n=Count("id"))),
        "find_total": find_qs.count(),
        "find_open": find_qs.exclude(status=AuditFinding.STATUS_CLOSED).count(),
        "last_run": AuditRun.objects.order_by("-started_at").first(),
        "tests_active": AuditTest.objects.filter(is_active=True).count(),
        "open_high": exc_qs.filter(status="open",
                                   risk_level="High").count(),
    }
    return render(request, "audit/cycle_hub.html", ctx)


@require_permission("exceptions.view")
def exception_detail(request, pk):
    exc = get_object_or_404(
        AuditException.objects.select_related(
            "test", "run", "handled_by"), pk=pk)
    from apps.accounts.permissions import has_perm
    # source snapshot for the chain → source transaction
    source_obj, source_desc, source_url = None, "", ""
    if exc.source_type == "expense":
        from apps.expenses.models import Expense
        source_obj = Expense.objects.filter(pk=exc.source_id).first()
        if source_obj:
            source_url = f"/expenses/{source_obj.pk}/"
            source_desc = str(source_obj)
    elif exc.source_type == "procurement":
        from apps.procurement.models import Procurement
        source_obj = Procurement.objects.filter(pk=exc.source_id).first()
        if source_obj:
            source_url = f"/procurement/{source_obj.pk}/"
            source_desc = str(source_obj)
    evidence_form = EvidenceUploadForm()
    return render(request, "audit/exception_detail.html", {
        "exc": exc,
        "source_obj": source_obj,
        "source_desc": source_desc,
        "source_url": source_url,
        "test": exc.test,
        "findings": exc.linked_findings.all(),
        "evidence_form": evidence_form,
        "can_manage": has_perm(request.user, "exceptions.manage"),
        "can_findings": has_perm(request.user, "findings.manage"),
        "bands": (exc.test.parameters or {}).get("risk_bands", {}),
    })


@require_permission("exceptions.manage")
@require_POST
def exception_evidence_upload(request, pk):
    exc = get_object_or_404(AuditException, pk=pk)
    form = EvidenceUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        for errs in form.errors.values():
            for msg in errs:
                messages.error(request, msg)
        return redirect("audit:exception_detail", exc.pk)
    if exc.evidence:
        exc.evidence.delete(save=False)  # replace previous upload
    exc.evidence = form.cleaned_data["evidence"]
    exc.save(update_fields=["evidence"])
    log_action(action="entity_updated", entity_type="audit_exception",
               entity_id=exc.pk,
               diff={"evidence_uploaded": exc.evidence.name},
               request=request)
    messages.success(request, "رُفع الدليل وربطه بالاستثناء.")
    return redirect("audit:exception_detail", exc.pk)


@require_permission("exceptions.view")
def exception_evidence_view(request, pk):
    exc = get_object_or_404(AuditException, pk=pk)
    if not exc.evidence:
        messages.error(request, "لا يوجد دليل مرفق بهذا الاستثناء.")
        return redirect("audit:exception_detail", exc.pk)
    log_action(action="exception_evidence_viewed",
               entity_type="audit_exception", entity_id=exc.pk,
               diff={"file": exc.evidence.name}, request=request)
    exc.evidence.open("rb")
    return FileResponse(exc.evidence, as_attachment=True,
                        filename=exc.evidence.name.split("/")[-1])


# ---------------------------------------------------------------- findings
@require_permission("findings.view")
def findings_list(request):
    from apps.accounts.permissions import has_perm
    qs = AuditFinding.objects.prefetch_related("exceptions")
    sel = {"status": request.GET.get("status", ""),
           "risk": request.GET.get("risk", ""),
           "q": request.GET.get("q", "").strip()}
    if sel["status"]:
        qs = qs.filter(status=sel["status"])
    if sel["risk"]:
        qs = qs.filter(risk_level=sel["risk"])
    if sel["q"]:
        from django.db.models import Q
        qs = qs.filter(Q(title__icontains=sel["q"])
                       | Q(finding_code__icontains=sel["q"])
                       | Q(recommendation__icontains=sel["q"]))
    return render(request, "audit/findings_list.html", {
        "findings": qs[:300], "sel": sel,
        "can_manage": has_perm(request.user, "findings.manage"),
    })


@require_permission("findings.view")
def finding_detail(request, pk):
    finding = get_object_or_404(
        AuditFinding.objects.prefetch_related("exceptions__test"),
        pk=pk)
    return render(request, "audit/finding_detail.html", {
        "finding": finding,
        "exceptions": finding.exceptions.all(),
    })


def _worst_risk(exceptions) -> str:
    order = {"High": 3, "Medium": 2, "Low": 1}
    risks = [e.risk_level for e in exceptions]
    return max(risks, key=lambda r: order.get(r, 0)) if risks else "Medium"


@require_permission("findings.manage")
def finding_create(request):
    exceptions = []
    exc_id = request.GET.get("exception") or request.POST.get("exception")
    if exc_id:
        exceptions = list(AuditException.objects.filter(pk=exc_id))
    initial = {}
    if exceptions:
        exc = exceptions[0]
        initial = {
            "title": f"{exc.test_code} — {exc.title}",
            "criteria": (exc.test.rule_text if exc.test else ""),
            "condition": exc.explanation,
            "risk_level": _worst_risk(exceptions),
        }
    form = FindingForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        finding = form.save(commit=False)
        finding.finding_code = engine.next_finding_code()
        finding.created_by = request.user
        finding.updated_by = request.user
        finding.save()
        if exceptions:
            finding.exceptions.set(exceptions)
        log_action(action="entity_created", entity_type="audit_finding",
                   entity_id=finding.pk,
                   diff={"finding_code": finding.finding_code,
                         "title": finding.title,
                         "risk_level": finding.risk_level,
                         "exceptions": [e.pk for e in exceptions]},
                   request=request)
        messages.success(
            request,
            f"أُنشئت النتيجة {finding.finding_code} وربطت "
            f"بـ{len(exceptions)} استثناء.")
        return redirect("audit:finding_detail", finding.pk)
    return render(request, "audit/finding_form.html", {
        "form": form, "creating": True, "exceptions": exceptions,
    })


@require_permission("findings.manage")
def finding_edit(request, pk):
    finding = get_object_or_404(AuditFinding, pk=pk)
    form = FindingForm(request.POST or None, instance=finding)
    if request.method == "POST" and form.is_valid():
        before = {"status": finding.status,
                  "risk_level": finding.risk_level}
        finding = form.save(commit=False)
        finding.updated_by = request.user
        finding.save()
        log_action(action="entity_updated", entity_type="audit_finding",
                   entity_id=finding.pk,
                   diff={"finding_code": finding.finding_code,
                         "before": before,
                         "after": {"status": finding.status,
                                   "risk_level": finding.risk_level}},
                   request=request)
        messages.success(request,
                         f"حُفظت النتيجة {finding.finding_code}.")
        return redirect("audit:finding_detail", finding.pk)
    return render(request, "audit/finding_form.html", {
        "form": form, "creating": False, "finding": finding,
        "exceptions": finding.exceptions.all(),
    })
