from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import connections, models, transaction
from django.utils import timezone

from apps.governance.models import CloudSyncRecordState, CloudSyncRun


MODEL_LABELS = (
    "accounts.User",
    "accounts.Role",
    "accounts.Permission",
    "reference.Currency",
    "reference.OrganizationSettings",
    "reference.FiscalYear",
    "reference.MonthlyPeriod",
    "reference.Department",
    "reference.Employee",
    "reference.ExpenseCategory",
    "reference.Account",
    "reference.Supplier",
    "accounts.UserRole",
    "accounts.RolePermission",
    "budget.Budget",
    "budget.BudgetVersion",
    "budget.BudgetLine",
    "budget.BudgetPlan",
    "budget.BudgetPlanSection",
    "budget.BudgetPlanLine",
    "budget.BudgetPlanPeriodAmount",
    "budget.BudgetTemplate",
    "budget.BudgetTemplateSheet",
    "budget.BudgetTemplateColumn",
    "budget.BudgetTemplateRow",
    "budget.BudgetTemplateCell",
    "expenses.Expense",
    "procurement.Procurement",
    "procurement.Quotation",
    "imports.ImportJob",
    "imports.DetailedBudgetSheet",
    "audit_register.AuditTest",
    "audit_register.AuditRun",
    "audit_register.AuditTestResult",
    "audit_register.AuditException",
    "audit_register.AuditFinding",
    "governance.Attachment",
    "governance.AuditLog",
)

VOLATILE_FIELDS = {"created_at", "updated_at", "last_login"}
LOCK_ID = 785214903


class CloudSyncUnavailable(RuntimeError):
    pass


class CloudSyncBusy(RuntimeError):
    pass


def cloud_connection_status() -> tuple[bool, str]:
    if settings.DEPLOYMENT_ENV != "development":
        return False, "المزامنة متاحة في النسخة المحلية فقط."
    if getattr(settings, "LOCAL_DATA_SOURCE", "local") == "cloud":
        return False, "الوضع المتصل يستخدم قاعدة Supabase مباشرة؛ لا حاجة للمزامنة."
    if "cloud" not in settings.DATABASES:
        return False, "أضف SUPABASE_DATABASE_URL إلى ملف system/.env."
    try:
        with connections["cloud"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        return False, f"تعذر الاتصال بالسحابة: {exc}"
    return True, "الاتصال بقاعدة Supabase متاح."


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _payload(instance, *, include_volatile: bool = True) -> dict[str, Any]:
    values = {}
    for field in instance._meta.concrete_fields:
        if not include_volatile and field.name in VOLATILE_FIELDS:
            continue
        values[field.attname] = getattr(instance, field.attname)
    return values


def _payload_hash(model, values: dict[str, Any]) -> str:
    ignored = {model._meta.pk.attname}
    ignored.update(
        field.attname
        for field in model._meta.concrete_fields
        if field.name in VOLATILE_FIELDS
    )
    payload = {
        key: _json_value(value)
        for key, value in values.items()
        if key not in ignored
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _record_hash(instance) -> str:
    return _payload_hash(instance.__class__, _payload(instance))


def _remap_payload(instance, pk_maps: dict[str, dict[Any, Any]]) -> dict[str, Any]:
    values = _payload(instance)
    for field in instance._meta.concrete_fields:
        if not field.is_relation or not field.many_to_one and not field.one_to_one:
            continue
        value = values.get(field.attname)
        if value is None:
            continue
        related_label = field.remote_field.model._meta.label
        values[field.attname] = pk_maps.get(related_label, {}).get(value, value)
    return values


def _unique_field_sets(model) -> list[tuple[str, ...]]:
    result = [
        (field.attname,)
        for field in model._meta.concrete_fields
        if field.unique and not field.primary_key
    ]
    result.extend(
        tuple(model._meta.get_field(name).attname for name in names)
        for names in model._meta.unique_together
    )
    result.extend(
        tuple(model._meta.get_field(name).attname for name in constraint.fields)
        for constraint in model._meta.total_unique_constraints
        if constraint.fields
    )
    return result


def _find_natural_match(manager, model, values: dict[str, Any]):
    for field_names in _unique_field_sets(model):
        lookup = {name: values.get(name) for name in field_names}
        if any(value in (None, "") for value in lookup.values()):
            continue
        match = manager.filter(**lookup).first()
        if match is not None:
            return match
    return None


def _decide_action(
    *,
    local_hash: str | None,
    cloud_hash: str,
    previous_cloud_hash: str | None,
) -> str:
    if local_hash is None:
        return "add"
    if local_hash == cloud_hash:
        return "unchanged"
    if previous_cloud_hash is None:
        return "conflict"
    if cloud_hash == previous_cloud_hash:
        return "preserve_local"
    if local_hash == previous_cloud_hash:
        return "update"
    return "conflict"


def _acquire_lock() -> None:
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [LOCK_ID])
        if not cursor.fetchone()[0]:
            raise CloudSyncBusy("توجد عملية مزامنة أخرى قيد التنفيذ.")


def _reset_sequence(model) -> None:
    table = model._meta.db_table
    pk_column = model._meta.pk.column
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", [table, pk_column])
        sequence = cursor.fetchone()[0]
        if sequence:
            cursor.execute(
                f'SELECT setval(%s, COALESCE(MAX("{pk_column}"), 1), '
                f'MAX("{pk_column}") IS NOT NULL) FROM "{table}"',
                [sequence],
            )


def _sync_model(
    model,
    summary: dict[str, Any],
    pk_maps: dict[str, dict[Any, Any]],
) -> None:
    label = model._meta.label
    counts = {
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "local_preserved": 0,
        "conflicts": 0,
    }
    local_manager = model._default_manager.using("default")
    model_pk_map = pk_maps.setdefault(label, {})

    for cloud_object in model._default_manager.using("cloud").all().iterator(chunk_size=500):
        object_pk = str(cloud_object.pk)
        cloud_values = _remap_payload(cloud_object, pk_maps)
        cloud_hash = _payload_hash(model, cloud_values)
        local_object = local_manager.filter(pk=cloud_object.pk).first()
        if local_object is None:
            local_object = _find_natural_match(local_manager, model, cloud_values)
        if local_object is not None:
            model_pk_map[cloud_object.pk] = local_object.pk
        state = CloudSyncRecordState.objects.filter(
            model_label=label,
            object_pk=object_pk,
        ).first()

        local_hash = _record_hash(local_object) if local_object is not None else None
        action = _decide_action(
            local_hash=local_hash,
            cloud_hash=cloud_hash,
            previous_cloud_hash=state.cloud_hash if state else None,
        )

        if action == "add":
            local_manager.bulk_create([model(**cloud_values)])
            model_pk_map[cloud_object.pk] = cloud_object.pk
            counts["added"] += 1
        elif action == "unchanged":
            counts["unchanged"] += 1
        elif action == "preserve_local":
            counts["local_preserved"] += 1
            continue
        elif action == "update":
            update_values = {
                field.attname: cloud_values[field.attname]
                for field in model._meta.concrete_fields
                if field.name not in VOLATILE_FIELDS
            }
            update_values.pop(model._meta.pk.attname, None)
            local_manager.filter(pk=local_object.pk).update(**update_values)
            counts["updated"] += 1
        else:
            counts["conflicts"] += 1
            summary["conflict_records"].append(f"{label}#{object_pk}")
            continue

        CloudSyncRecordState.objects.update_or_create(
            model_label=label,
            object_pk=object_pk,
            defaults={"cloud_hash": cloud_hash},
        )

    _reset_sequence(model)
    summary["models"][label] = counts
    for key in counts:
        summary[key] += counts[key]


def _sync_finding_exceptions(
    summary: dict[str, Any],
    pk_maps: dict[str, dict[Any, Any]],
) -> None:
    finding_model = apps.get_model("audit_register.AuditFinding")
    exception_model = apps.get_model("audit_register.AuditException")
    through = finding_model.exceptions.through
    cloud_rows = list(
        through._default_manager.using("cloud").values_list(
            "auditfinding_id", "auditexception_id"
        )
    )
    local_rows = set(
        through._default_manager.using("default").values_list(
            "auditfinding_id", "auditexception_id"
        )
    )
    valid_findings = set(
        finding_model.objects.using("default").values_list("pk", flat=True)
    )
    valid_exceptions = set(
        exception_model.objects.using("default").values_list("pk", flat=True)
    )
    finding_map = pk_maps.get(finding_model._meta.label, {})
    exception_map = pk_maps.get(exception_model._meta.label, {})
    remapped_rows = [
        (
            finding_map.get(finding_id, finding_id),
            exception_map.get(exception_id, exception_id),
        )
        for finding_id, exception_id in cloud_rows
    ]
    additions = [
        through(auditfinding_id=finding_id, auditexception_id=exception_id)
        for finding_id, exception_id in remapped_rows
        if (finding_id, exception_id) not in local_rows
        and finding_id in valid_findings
        and exception_id in valid_exceptions
    ]
    through._default_manager.using("default").bulk_create(
        additions,
        ignore_conflicts=True,
    )
    summary["m2m_added"] = len(additions)


def storage_sync_configured() -> bool:
    return all(
        os.environ.get(name, "").strip()
        for name in (
            "SUPABASE_S3_ACCESS_KEY_ID",
            "SUPABASE_S3_SECRET_ACCESS_KEY",
            "SUPABASE_PROJECT_REF",
            "SUPABASE_STORAGE_BUCKET",
        )
    )


def _safe_media_path(name: str) -> Path:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    destination = (media_root / name).resolve()
    if media_root != destination and media_root not in destination.parents:
        raise ValueError(f"مسار ملف غير آمن: {name}")
    return destination


def _sync_files(summary: dict[str, Any]) -> None:
    if not storage_sync_configured():
        raise CloudSyncUnavailable(
            "مفتاح Supabase S3 المحلي غير مهيأ؛ تمت مزامنة السجلات فقط."
        )
    from storages.backends.s3 import S3Storage

    endpoint = os.environ.get("SUPABASE_STORAGE_ENDPOINT", "").strip()
    if not endpoint:
        endpoint = (
            f"https://{os.environ['SUPABASE_PROJECT_REF']}"
            ".storage.supabase.co/storage/v1/s3"
        )
    cloud_storage = S3Storage(
        access_key=os.environ["SUPABASE_S3_ACCESS_KEY_ID"],
        secret_key=os.environ["SUPABASE_S3_SECRET_ACCESS_KEY"],
        bucket_name=os.environ["SUPABASE_STORAGE_BUCKET"],
        endpoint_url=endpoint,
        region_name=os.environ.get("SUPABASE_STORAGE_REGION", "ap-northeast-2"),
        addressing_style="path",
        signature_version="s3v4",
    )
    local_storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    copied = 0
    for label in MODEL_LABELS:
        model = apps.get_model(label)
        file_fields = [
            field
            for field in model._meta.concrete_fields
            if isinstance(field, models.FileField)
        ]
        for field in file_fields:
            names = (
                model._default_manager.using("default")
                .exclude(**{field.name: ""})
                .values_list(field.name, flat=True)
            )
            for name in names.iterator():
                if not name or local_storage.exists(name):
                    continue
                destination = _safe_media_path(name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(destination.suffix + ".part")
                with cloud_storage.open(name, "rb") as source, temporary.open("wb") as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        target.write(chunk)
                temporary.replace(destination)
                copied += 1
    summary["files_copied"] = copied


def sync_cloud_to_local(*, started_by=None, include_files: bool = False) -> CloudSyncRun:
    available, message = cloud_connection_status()
    if not available:
        raise CloudSyncUnavailable(message)

    run = CloudSyncRun.objects.create(started_by=started_by, status="running")
    summary = {
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "local_preserved": 0,
        "conflicts": 0,
        "m2m_added": 0,
        "files_copied": 0,
        "models": {},
        "conflict_records": [],
    }
    try:
        with transaction.atomic(using="default"):
            _acquire_lock()
            with connections["default"].cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL DEFERRED")
            pk_maps: dict[str, dict[Any, Any]] = {}
            for label in MODEL_LABELS:
                _sync_model(apps.get_model(label), summary, pk_maps)
            _sync_finding_exceptions(summary, pk_maps)
        if include_files:
            _sync_files(summary)
        run.status = "partial" if summary["conflicts"] else "completed"
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.summary = summary
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error", "summary", "completed_at"])
        raise
    run.summary = summary
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "summary", "completed_at"])
    return run
