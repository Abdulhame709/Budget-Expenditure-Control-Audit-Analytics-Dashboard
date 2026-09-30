"""Production settings — fail fast on missing secrets (foundation for PHASE 15)."""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

# SECRET_KEY must exist AND must not be a placeholder — .env files often
# ship "change-me…" which would otherwise silently satisfy a presence check.
_secret = os.environ.get("DJANGO_SECRET_KEY", "")
_insecure_markers = ("change-me", "change_me", "django-insecure",
                     "replace-me", "do-not-use", "insecure")
if not _secret:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")
if len(_secret) < 50 or any(m in _secret.lower() for m in _insecure_markers):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is an insecure placeholder — generate a real one "
        "(≥50 chars): python -c \"import secrets; print(secrets.token_urlsafe(50))\""
    )
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

# Static files through WhiteNoise (no web-server alias required).
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# Security flags — env-driven so a TLS-terminating proxy can enable them.
_sec = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "false").lower() == "true"
SECURE_SSL_REDIRECT = _sec
SESSION_COOKIE_SECURE = _sec
CSRF_COOKIE_SECURE = _sec
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.environ.get("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "false").lower()
    == "true")
SECURE_HSTS_PRELOAD = (
    os.environ.get("DJANGO_SECURE_HSTS_PRELOAD", "false").lower() == "true")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Extra origins allowed to POST (scheme://host, comma-separated) —
# needed when the public domain differs from the app host.
_csrf_origins = [
    o.strip() for o in
    os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = _csrf_origins
