"""PHASE 9/10 forms — audit test definition + Finding lifecycle + evidence."""
from __future__ import annotations

import json

from django import forms
from django.core.exceptions import ValidationError

from apps.audit_register.models import AuditException, AuditFinding, AuditTest
from apps.audit_register.services import ENGINE_CHOICES
from apps.imports.services import MAX_FILE_MB


class AuditTestForm(forms.ModelForm):
    parameters_json = forms.CharField(
        label="Parameters — المعاملات (JSON)",
        widget=forms.Textarea(attrs={
            "class": "form-control font-monospace", "rows": 6, "dir": "ltr"}),
        help_text=(
            "كل العتبات تُقرأ من هنا وقت التشغيل (ليست hard-coded). "
            "يجب أن يحوي المفتاح synthetic_rule=true للقواعد التدريبية. "
            "risk_bands: {\"a3\": 10000, \"a2\": 2000} لمعادلة الخطر 3×3."),
        required=True)

    class Meta:
        model = AuditTest
        fields = [
            "test_code", "name", "domain", "objective", "rule_text",
            "data_source", "expected_result", "exception_type",
            "default_risk", "auditor_action", "is_active", "engine_key",
            "synthetic_rule",
        ]
        widgets = {
            "test_code": forms.TextInput(attrs={
                "class": "form-control", "dir": "ltr",
                "placeholder": "T-EXP-07"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "domain": forms.Select(attrs={"class": "form-select"}),
            "objective": forms.Textarea(attrs={
                "class": "form-control", "rows": 2}),
            "rule_text": forms.Textarea(attrs={
                "class": "form-control", "rows": 4}),
            "data_source": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "expenses; budget_lines …"}),
            "expected_result": forms.Textarea(attrs={
                "class": "form-control", "rows": 2}),
            "exception_type": forms.TextInput(attrs={"class": "form-control"}),
            "default_risk": forms.Select(attrs={"class": "form-select"}),
            "auditor_action": forms.Textarea(attrs={
                "class": "form-control", "rows": 2}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "synthetic_rule": forms.CheckboxInput(
                attrs={"class": "form-check-input"}),
            "engine_key": forms.Select(
                choices=ENGINE_CHOICES,
                attrs={"class": "form-select"}),
        }
        labels = {
            "test_code": "Test ID",
            "is_active": "Active — مفعّل",
            "synthetic_rule": "قاعدة تدريبية (Synthetic/Training Rule)",
            "engine_key": "محرّك التنفيذ",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.fields:
            if name == "parameters_json":
                continue
            if hasattr(self.fields[name], "error_messages"):
                self.fields[name].error_messages["required"] = (
                    "هذا الحقل مطلوب.")
        if self.instance and self.instance.pk and self.instance.parameters:
            self.initial.setdefault(
                "parameters_json",
                json.dumps(self.instance.parameters, ensure_ascii=False,
                           indent=2))
        elif "parameters_json" not in self.initial:
            self.initial["parameters_json"] = json.dumps({
                "synthetic_rule": True,
                "risk_bands": {"a3": 10000, "a2": 2000},
            }, ensure_ascii=False, indent=2)

    def clean_test_code(self):
        value = (self.cleaned_data.get("test_code") or "").strip().upper()
        qs = AuditTest.objects.filter(test_code=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Test ID مستخدم مسبقًا — اختر معرّفًا فريدًا.")
        return value

    def clean_parameters_json(self):
        raw = self.cleaned_data.get("parameters_json") or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"JSON غير صالح: {exc}") from exc
        if not isinstance(data, dict):
            raise ValidationError("يجب أن تكون المعاملات كائنًا (dict) JSON.")
        return data

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("synthetic_rule") is False:
            # never silently claim a real policy
            raise ValidationError(
                "إلغاء علامة «قاعدة تدريبية» يتطلب توثيقًا خارج النظام — "
                "الافتراض المعتمد لهذه المرحلة أن كل القواعد Synthetic. "
                "راجع المالك قبل تغيير هذه العلامة.")
        return cleaned


# ================================================================ PHASE 10
class FindingForm(forms.ModelForm):
    class Meta:
        model = AuditFinding
        fields = [
            "title", "criteria", "condition", "impact", "cause",
            "cause_supported", "risk_level", "recommendation",
            "management_action", "status", "status_note",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "criteria": forms.Textarea(attrs={"class": "form-control",
                                              "rows": 3}),
            "condition": forms.Textarea(attrs={"class": "form-control",
                                               "rows": 3}),
            "impact": forms.Textarea(attrs={"class": "form-control",
                                            "rows": 2}),
            "cause": forms.Textarea(attrs={"class": "form-control",
                                           "rows": 2}),
            "cause_supported": forms.CheckboxInput(
                attrs={"class": "form-check-input"}),
            "risk_level": forms.Select(attrs={"class": "form-select"}),
            "recommendation": forms.Textarea(attrs={"class": "form-control",
                                                    "rows": 3}),
            "management_action": forms.Textarea(
                attrs={"class": "form-control", "rows": 2}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "status_note": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.error_messages["required"] = "هذا الحقل مطلوب."
        self.fields["cause_supported"].required = False
        self.fields["management_action"].required = False
        self.fields["status_note"].required = False
        self.fields["cause"].required = False

    def clean(self):
        cleaned = super().clean()
        cause = (cleaned.get("cause") or "").strip()
        supported = cleaned.get("cause_supported")
        if cause and not supported:
            raise ValidationError(
                "السبب (Cause) لا يُكتب إلا مع دليل يدعمه — فعّل "
                "«السبب مدعوم بدليل» أو اترك الحقل فارغًا "
                "(شرط: Cause only when supported).")
        if not cause:
            cleaned["cause_supported"] = False
        return cleaned


class EvidenceUploadForm(forms.Form):
    evidence = forms.FileField(
        label="Evidence — دليل داعم (≤10MB)",
        widget=forms.FileInput(attrs={
            "class": "form-control",
            "accept": ".pdf,.png,.jpg,.jpeg,.xlsx,.csv,.txt"}))

    def clean_evidence(self):
        upload = self.cleaned_data["evidence"]
        if upload.size > MAX_FILE_MB * 1024 * 1024:
            raise ValidationError(
                f"حجم الدليل يتجاوز الحد الأقصى ({MAX_FILE_MB} ميجابايت).")
        return upload
