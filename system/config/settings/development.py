"""Development settings — DEBUG on, permissive hosts, safe dev defaults."""
import os

# Provide the dev DATABASE_URL BEFORE importing base (base requires it).
os.environ.setdefault(
    "DATABASE_URL",
    "postgres://audit_user:audit_pass@127.0.0.1:5432/audit_budget_system",
)

from .base import *  # noqa: F401,F403,E402

DEBUG = True
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "https://*.e2b.app",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://0.0.0.0:8000",
]

# Insecure-by-design development key; production.py refuses to start without a real one.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "django-insecure-dev-only-do-not-use-in-production"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

LOGGING["loggers"]["django.db.backends"] = {"level": "WARNING", "propagate": True}
