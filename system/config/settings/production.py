"""Production settings for Vercel deployment."""
import os
from django.core.exceptions import ImproperlyConfigured

os.environ.setdefault("SYSTEM_MODE", "operational")
os.environ.setdefault("DJANGO_ALLOW_SYNTHETIC_DATASET", "false")

from .base import *  # noqa: F401,F403

DEBUG = False
DEPLOYMENT_ENV = "production"

# SECRET_KEY: use env var if valid, else fallback
_secret_env = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if _secret_env and len(_secret_env) >= 50:
    SECRET_KEY = _secret_env
else:
    SECRET_KEY = "a8f5f167f44f4964e6c998dee827110c8f5f167f44f4964e6c998dee827110c8f5f167f44f4964e6c998dee827110c"

# ALLOWED_HOSTS: allow all Vercel subdomains
_vercel_url = os.environ.get("VERCEL_URL", "").strip().lower().rstrip(".")
if _vercel_url:
    if _vercel_url.startswith("https://"):
        _vercel_url = _vercel_url[8:]
    elif _vercel_url.startswith("http://"):
        _vercel_url = _vercel_url[7:]
    _vercel_url = _vercel_url.rstrip("/")
    if ":" in _vercel_url:
        _vercel_url = _vercel_url.split(":")[0]
    ALLOWED_HOSTS = [_vercel_url, ".vercel.app"]
    CSRF_TRUSTED_ORIGINS = [f"https://{_vercel_url}", "https://*.vercel.app"]
else:
    ALLOWED_HOSTS = [".vercel.app"]
    CSRF_TRUSTED_ORIGINS = ["https://*.vercel.app"]

# Persistent import files and static files
_storage_access_key = os.environ.get("SUPABASE_S3_ACCESS_KEY_ID", "").strip()
_storage_secret_key = os.environ.get("SUPABASE_S3_SECRET_ACCESS_KEY", "").strip()
_storage_bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "audit-imports").strip()
_storage_region = os.environ.get("SUPABASE_STORAGE_REGION", "ap-northeast-2").strip()
_storage_endpoint = os.environ.get("SUPABASE_STORAGE_ENDPOINT", "").strip()
if not _storage_endpoint and SUPABASE_PROJECT_REF:
    _storage_endpoint = (
        f"https://{SUPABASE_PROJECT_REF}.storage.supabase.co/storage/v1/s3"
    )

IMPORT_FILE_STORAGE_CONFIGURED = all((
    _storage_access_key,
    _storage_secret_key,
    _storage_bucket,
    _storage_region,
    _storage_endpoint,
))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
if IMPORT_FILE_STORAGE_CONFIGURED:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": _storage_access_key,
            "secret_key": _storage_secret_key,
            "bucket_name": _storage_bucket,
            "endpoint_url": _storage_endpoint,
            "region_name": _storage_region,
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }

# Security
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Logging
LOGGING["handlers"].pop("file", None)
LOGGING["root"]["handlers"] = ["console"]

ALLOW_SELF_REGISTRATION = False

