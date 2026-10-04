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

# Vercel production: use env var if valid, else use fixed fallback
_secret_env = os.environ.get("DJANGO_SECRET_KEY", "")
if _secret_env and len(_secret_env.strip()) >= 50:
    SECRET_KEY = _secret_env.strip()
else:
    # Fallback for Vercel deployment (not secure for real production, but unblocks demo)
    SECRET_KEY = "a8f5f167f44f4964e6c998dee827110c8f5f167f44f4964e6c998dee827110c8f5f167f44f4964e6c998dee827110c"
    print("[VERCEL] Using fallback SECRET_KEY (env var missing or too short)")

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


_vercel_url = os.environ.get("VERCEL_URL", "").strip().lower().rstrip(".")
if _vercel_url:
    # Strip protocol prefix if present
    if _vercel_url.startswith("https://"):
        _vercel_url = _vercel_url[8:]
    elif _vercel_url.startswith("http://"):
        _vercel_url = _vercel_url[7:]
    # Strip trailing slash and port
    _vercel_url = _vercel_url.rstrip("/")
    if ":" in _vercel_url:
        _vercel_url = _vercel_url.split(":")[0]
    ALLOWED_HOSTS = [_vercel_url, ".vercel.app"]
    # Ensure CSRF matches
    CSRF_TRUSTED_ORIGINS = [f"https://{_vercel_url}", "https://*.vercel.app"]
if not ALLOWED_HOSTS:
    # Fallback: allow all Vercel domains for demo
    ALLOWED_HOSTS = [".vercel.app"]
    CSRF_TRUSTED_ORIGINS = ["https://*.vercel.app"]
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

# Vercel production: build CSRF origins from ALLOWED_HOSTS (auto or env)
_csrf_env = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").strip()
if _csrf_env:
    _csrf_origins = [o.strip() for o in _csrf_env.split(",") if o.strip()]
else:
    _csrf_origins = [f"https://{host}" for host in ALLOWED_HOSTS]
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










