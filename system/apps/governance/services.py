"""Audit Trail service — the single entry point for logging sensitive actions.

Rules:
- append-only (create() only; the model is never updated/deleted by the app)
- never logs secrets (callers must not put passwords in `diff` — see guards)
- captures actor snapshot + IP/user-agent when a request is available
"""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from apps.governance.models import AuditLog

log = logging.getLogger("governance.audit")

_SECRET_KEYS = ("password", "secret", "token", "hash")


def _scrub(diff: dict) -> dict:
    """Defense-in-depth: drop any secret-looking keys from the diff."""
    return {k: v for k, v in (diff or {}).items()
            if not any(s in str(k).lower() for s in _SECRET_KEYS)}


def client_ip(request) -> str:
    if request is None:
        return ""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
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
    """Record one sensitive operation. Returns the created AuditLog row."""
    if actor is None and request is not None:
        actor = getattr(request, "user", None)
        if actor is not None and not actor.is_authenticated:
            actor = None

    context = {}
    if request is not None:
        context["ip"] = client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")
        context["user_agent"] = ua[:200]
    if extra_context:
        context.update(extra_context)

    entry = AuditLog.objects.create(
        actor=actor,
        actor_label=(getattr(actor, "username", "") or ""),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        diff=_scrub(diff or {}),
        context=context,
    )
    log.info("audit: %s %s#%s by %s", action, entity_type, entity_id,
             entry.actor_label or "system")
    return entry


def log_login_failure(username: str, request=None) -> AuditLog:
    """Failed login attempts are security-relevant too (no password logged)."""
    return log_action(
        action="login_failed",
        entity_type="user",
        entity_id=username[:60],
        diff={"username": username[:150], "reason": "invalid_credentials"},
        request=request,
        actor=None,
    )
