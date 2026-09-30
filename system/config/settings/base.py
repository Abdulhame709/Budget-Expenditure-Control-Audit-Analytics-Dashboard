"""
Base settings for Audit Analytics & Budget Control System (PHASE 2).
Approved architecture: Django + PostgreSQL (D-01) — no SQLite, ever.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]  # system/ (…/system/config/settings/base.py)
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------- identity
SYSTEM_NAME_AR = "نظام التحليل الرقابي والموازنة والمصروفات والمشتريات"
SYSTEM_NAME_EN = "Audit Analytics & Budget Control System"
SYSTEM_OWNER = "Abdulhameed — Internal Audit & Financial Review Professional"
SYSTEM_CONTEXT = "Professional Proof-of-Work / Training & Demonstration System"
DEMO_NOTICE = "بيانات تدريبية Synthetic Training Data — ليست بيانات شركة حقيقية"

# ---------------------------------------------------------------- core
# SECRET_KEY: development.py provides an insecure default; production.py requires it.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY and not os.environ.get("DJANGO_SECRET_KEY"):
    pass  # production.py enforces; development.py sets fallback after import.

DEBUG = False

ALLOWED_HOSTS: list[str] = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]

# ---------------------------------------------------------------- database
# D-01: PostgreSQL is the only database. Missing DATABASE_URL in production = hard error.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise ImproperlyConfigured(
        "DATABASE_URL is not set. PostgreSQL is mandatory (decision D-01) — "
        "copy .env.example to .env and configure it."
    )
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ---------------------------------------------------------------- apps
DJANGO_APPS = [
    "django.contrib.admin",  # lightweight ops tool; module UIs are built in later phases
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.reference",
    "apps.budget",
    "apps.expenses",
    "apps.procurement",
    "apps.imports",
    "apps.analytics",
    "apps.audit_register",
    "apps.reports",
    "apps.governance",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.AccessControlMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.system_identity",
            ],
        },
    },
]

# ---------------------------------------------------------------- auth (foundation)
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/accounts/login/"  # wired in the authentication phase
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------- i18n / time
LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Aden"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- static / media
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- logging foundation
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name} :: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "django.log",
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
    "loggers": {
        "django": {"level": "INFO", "propagate": True},
        "django.request": {"level": "WARNING", "propagate": True},
        "django.db.backends": {"level": "WARNING", "propagate": True},
    },
}

# ---------------------------------------------------------------- error pages (foundation)
DEFAULT_EXCEPTION_REPORTER = "django.views.debug.ExceptionReporter"
