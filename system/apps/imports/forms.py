"""PHASE 8 — import forms (upload + column mapping)."""
from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from apps.imports.models import ImportJob
from apps.imports.services import MAX_FILE_MB, detect_format


class ImportUploadForm(forms.Form):
    target = forms.ChoiceField(
        label="الهدف",
        choices=ImportJob.TARGET_CHOICES,
        initial=ImportJob.TARGET_EXPENSES,
        widget=forms.Select(attrs={"class": "form-select"}))
    source_file = forms.FileField(
        label="الملف (CSV / Excel xlsx / PDF)",
        widget=forms.FileInput(attrs={
            "class": "form-control", "accept": ".csv,.xlsx,.pdf"}))

    def clean_source_file(self):
        upload = self.cleaned_data["source_file"]
        detect_format(upload.name)  # Arabic error on unsupported extension
        if upload.size > MAX_FILE_MB * 1024 * 1024:
            raise ValidationError(
                f"حجم الملف يتجاوز الحد الأقصى ({MAX_FILE_MB} ميجابايت).")
        return upload


class MappingForm(forms.Form):
    """Dynamic target←header mapping — fields built in the view from headers."""

    def __init__(self, headers: list[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "— غير مطابق —")]
        choices += [(h, h) for h in headers]
        from apps.imports.services import TARGET_FIELDS, _REQUIRED
        self.required_keys = set(_REQUIRED)
        for key, label in TARGET_FIELDS:
            # not field-required on purpose: `clean()` raises ONE Arabic
            # message listing every unmapped required field.
            self.fields[key] = forms.ChoiceField(
                label=label, required=False, choices=choices,
                widget=forms.Select(attrs={"class": "form-select"}))

    def clean(self):
        cleaned = super().clean()
        missing = [
            self.fields[k].label for k in self.required_keys
            if not cleaned.get(k)]
        if missing:
            raise ValidationError(
                "الحقول التالية إلزامية ولا توجد لها مطابقة: "
                + "، ".join(missing))
        return cleaned
