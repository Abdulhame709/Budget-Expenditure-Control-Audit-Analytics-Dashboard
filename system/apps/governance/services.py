"""Audit Trail service — the single entry point for sensitive-operation logs.

The application only appends audit entries. Secret-like keys are scrubbed at
all nesting levels, and client IP attribution trusts the transport peer only.
"""
from __future__ import annotations

import logging

from apps.governance.models import AuditLog

log = logging.getLogger("governance.audit")
_SECRET_KEYS = ("password", "secret", "token", "hash", "credential", "authorization")


def _scrub(value):
    """Recursively remove secret-bearing keys from dict/list payloads."""
    if isinstance(value, dict):
        return {
            key: _scrub(item)
            for key, item in value.items()
            if not any(marker in str(key).lower() for marker in _SECRET_KEYS)
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value


def client_ip(request) -> str:
    """Use REMOTE_ADDR; X-Forwarded-For is untrusted unless proxy policy is proven."""
    if request is None:
        return ""
    return request.META.get("REMOTE_ADDR", "")


def log_action(
    *,
    action: str,
    entity_type: str,
    entity_id: str | int = "",
    diff: dict | None = None,
    request=None,
    actor=None,
    extra_context: dict | None = None,
) -> AuditLog:
    """Record one sensitive operation after recursively scrubbing its payload."""
    if actor is None and request is not None:
        actor = getattr(request, "user", None)
        if actor is not None and not actor.is_authenticated:
            actor = None

    context = {}
    if request is not None:
        context["ip"] = client_ip(request)
        context["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:200]
    if extra_context:
        context.update(extra_context)

    entry = AuditLog.objects.create(
        actor=actor,
        actor_label=getattr(actor, "username", "") or "",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        diff=_scrub(diff or {}),
        context=_scrub(context),
    )
    log.info("audit: %s %s#%s by %s", action, entity_type, entity_id,
             entry.actor_label or "system")
    return entry


def log_login_failure(username: str, request=None) -> AuditLog:
    """Failed logins remain auditable without logging a submitted password."""
    return log_action(
        action="login_failed",
        entity_type="user",
        entity_id=username[:60],
        diff={"username": username[:150], "reason": "invalid_credentials"},
        request=request,
        actor=None,
    )
