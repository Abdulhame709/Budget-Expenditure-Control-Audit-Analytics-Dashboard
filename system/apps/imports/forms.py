"""PHASE 8 — validated upload and column-mapping forms."""
from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile

from django import forms
from django.core.exceptions import ValidationError

from apps.imports.models import ImportJob
from apps.imports.services import MAX_FILE_MB, detect_format

MAX_XLSX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_XLSX_MEMBERS = 2_000


def _validate_file_bytes(upload, fmt: str) -> None:
    """Check signatures and bounded XLSX expansion without trusting MIME headers."""
    raw = upload.read()
    upload.seek(0)
    if fmt == "csv":
        if b"\x00" in raw or raw.startswith((b"%PDF-", b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
            raise ValidationError("محتوى الملف لا يطابق صيغة CSV النصية.")
        # Keep compatibility with common Arabic and Western encodings.
        for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
            try:
                raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:  # pragma: no cover - Latin-1 accepts all byte values
            raise ValidationError("تعذّر فك ترميز ملف CSV المدعوم.")
    elif fmt == "pdf":
        if raw[:1024].find(b"%PDF-") < 0:
            raise ValidationError("محتوى الملف لا يحمل ترويسة PDF صالحة.")
    elif fmt == "xlsx":
        if not raw.startswith(b"PK\x03\x04"):
            raise ValidationError("محتوى الملف لا يحمل حاوية Excel (xlsx) صالحة.")
        try:
            with ZipFile(BytesIO(raw)) as archive:
                members = archive.infolist()
                expanded = sum(member.file_size for member in members)
                if len(members) > MAX_XLSX_MEMBERS:
                    raise ValidationError("ملف Excel يحتوي عناصر أكثر من الحد المسموح.")
                if expanded > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise ValidationError("حجم محتوى Excel بعد فك الضغط يتجاوز الحد المسموح.")
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                    raise ValidationError("ملف Excel لا يحتوي بنية xlsx صالحة.")
        except BadZipFile as exc:
            raise ValidationError("ملف Excel المضغوط غير صالح.") from exc


class ImportUploadForm(forms.Form):
    target = forms.ChoiceField(
        label="الهدف",
        choices=ImportJob.TARGET_CHOICES,
        initial=ImportJob.TARGET_EXPENSES,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_target"}),
    )
    source_file = forms.FileField(
        label="الملف (CSV / Excel xlsx / PDF)",
        widget=forms.FileInput(attrs={
            "class": "form-control", "accept": ".csv,.xlsx,.pdf"}),
    )

    def clean(self):
        cleaned = super().clean()
        target = cleaned.get("target")
        upload = cleaned.get("source_file")
        if target == ImportJob.TARGET_DETAILED_BUDGET and upload is not None:
            name = (getattr(upload, "name", "") or "").lower()
            if not name.endswith(".xlsx"):
                self.add_error("source_file",
                               "الموازنة التفصيلية الأولية تقبل ملف Excel (xlsx) فقط.")
        return cleaned

    def clean_source_file(self):
        upload = self.cleaned_data["source_file"]
        fmt = detect_format(upload.name)
        if upload.size > MAX_FILE_MB * 1024 * 1024:
            raise ValidationError(
                f"حجم الملف يتجاوز الحد الأقصى ({MAX_FILE_MB} ميجابايت)."
            )
        _validate_file_bytes(upload, fmt)
        return upload


class MappingForm(forms.Form):
    """Dynamic target←header mapping; required targets share one Arabic error."""

    def __init__(self, headers: list[str], *args, target=ImportJob.TARGET_EXPENSES, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "— غير مطابق —")] + [(header, header) for header in headers]
        from apps.imports.services import get_required_fields, get_target_fields

        self.required_keys = set(get_required_fields(target))
        for key, label in get_target_fields(target):
            self.fields[key] = forms.ChoiceField(
                label=label,
                required=False,
                choices=choices,
                widget=forms.Select(attrs={"class": "form-select"}),
            )

    def clean(self):
        cleaned = super().clean()
        missing = [
            self.fields[key].label
            for key in self.required_keys
            if not cleaned.get(key)
        ]
        if missing:
            raise ValidationError(
                "الحقول التالية إلزامية ولا توجد لها مطابقة: " + "، ".join(missing)
            )
        return cleaned
