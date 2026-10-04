"""Production-like settings shared by staging and production.

These settings fail closed. Provider secrets, exact hostnames, database URLs,
and deployment-specific TLS choices belong in the hosting provider's secret
store, never in Git.
"""
import os
import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False
if DEPLOYMENT_ENV not in {"staging", "production"}:
    raise ImproperlyConfigured(
        "config.settings.production/staging requires DJANGO_ENV=staging or production."
    )

_secret = os.environ.get("DJANGO_SECRET_KEY", "")
print(f"[VERCEL DEBUG] DJANGO_SECRET_KEY length: {len(_secret)}")
print(f"[VERCEL DEBUG] DJANGO_SECRET_KEY stripped length: {len(_secret.strip())}")
if not _secret:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in staging/production.")
if len(_secret.strip()) < 50:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is too short; use a random key of at least 50 characters."
    )
SECRET_KEY = _secret.strip()

_HOST_LABEL = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")


def _is_exact_host(value: str) -> bool:
    """Accept an exact DNS-style hostname, never '*' or a wildcard subdomain."""
    host = value.strip().rstrip(".")
    if (
        not host
        or "*" in host
        or "://" in host
        or "/" in host
        or ":" in host
        or len(host) > 253
        or host.lower() in {"localhost", "localhost.localdomain", "127.0.0.1"}
    ):
        return False
    labels = host.split(".")
    return len(labels) >= 2 and all(_HOST_LABEL.fullmatch(label) for label in labels)


if os.environ.get("VERCEL_URL"):
    ALLOWED_HOSTS = [os.environ["VERCEL_URL"].strip().lower().rstrip(".")]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list exact staging/production hostnames."
    )
if any(not _is_exact_host(host) for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must contain exact DNS hostnames (no wildcard, URL, port, or localhost)."
    )

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean value.")


SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
if not SECURE_SSL_REDIRECT:
    raise ImproperlyConfigured(
        "HTTPS redirect cannot be disabled in staging/production settings."
    )
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60

SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False
)
SECURE_HSTS_PRELOAD = _env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured("DJANGO_SECURE_HSTS_SECONDS cannot be negative.")
if SECURE_HSTS_PRELOAD and (
    SECURE_HSTS_SECONDS < 31_536_000 or not SECURE_HSTS_INCLUDE_SUBDOMAINS
):
    raise ImproperlyConfigured(
        "HSTS preload requires at least one year and includeSubDomains; enable it only after domain review."
    )

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# This is safe only when the service is reachable exclusively through its TLS proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

_csrf_origins = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
_allowed_hosts_normalized = {host.lower().rstrip(".") for host in ALLOWED_HOSTS}
for origin in _csrf_origins:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname.lower().rstrip(".") not in _allowed_hosts_normalized
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or "*" in origin
    ):
        raise ImproperlyConfigured(
            "DJANGO_CSRF_TRUSTED_ORIGINS must contain exact HTTPS origins matching DJANGO_ALLOWED_HOSTS."
        )
CSRF_TRUSTED_ORIGINS = _csrf_origins

if DEPLOYMENT_ENV == "production":
    SYSTEM_CONTEXT = "Production application"
    DEMO_NOTICE = "" if IS_OPERATIONAL_MODE else "بيئة الإنتاج — لا تستخدم حسابات أو بيانات التدريب"
else:
    SYSTEM_CONTEXT = "Staging environment"
    DEMO_NOTICE = "" if IS_OPERATIONAL_MODE else "بيئة Staging — لا تُعامل بياناتها كبيانات إنتاج"

# Managed platforms should send logs to stdout/stderr, not ephemeral local files.
LOGGING["handlers"].pop("file", None)
LOGGING["root"]["handlers"] = ["console"]

# Production default: self-registration disabled unless explicitly enabled.
ALLOW_SELF_REGISTRATION = False





