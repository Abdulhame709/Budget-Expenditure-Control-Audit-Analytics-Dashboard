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

# Resolve the deployment environment from the settings module unless explicitly
# declared. An explicit mismatch is a startup error, never a silent downgrade.
_known_environments = {"development", "staging", "production"}
_settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "").rsplit(".", 1)[-1]
_explicit_environment = os.environ.get("DJANGO_ENV", "").strip().lower()
if _explicit_environment and _explicit_environment not in _known_environments:
    raise ImproperlyConfigured("DJANGO_ENV must be development, staging, or production.")
if (
    _settings_module in _known_environments
    and _explicit_environment
    and _settings_module != _explicit_environment
):
    raise ImproperlyConfigured(
        "DJANGO_ENV must match the selected DJANGO_SETTINGS_MODULE environment."
    )
DEPLOYMENT_ENV = (
    _settings_module if _settings_module in _known_environments
    else _explicit_environment or "development"
)
IS_SECURE_ENVIRONMENT = DEPLOYMENT_ENV in {"staging", "production"}
if IS_SECURE_ENVIRONMENT and _settings_module not in {"staging", "production"}:
    raise ImproperlyConfigured(
        "Staging/production environment must use config.settings.staging or .production."
    )
SYSTEM_MODE = os.environ.get("SYSTEM_MODE", "demo").strip().lower()
if SYSTEM_MODE not in {"demo", "operational"}:
    raise ImproperlyConfigured("SYSTEM_MODE must be demo or operational.")
IS_OPERATIONAL_MODE = SYSTEM_MODE == "operational"
ALLOW_SYNTHETIC_DATASET = (
    (not IS_OPERATIONAL_MODE and DEPLOYMENT_ENV == "development")
    or (
        not IS_OPERATIONAL_MODE
        and
        DEPLOYMENT_ENV == "staging"
        and os.environ.get("DJANGO_ALLOW_SYNTHETIC_DATASET", "false").strip().lower()
        == "true"
    )
)
READINESS_CHECK_TOKEN = os.environ.get("DJANGO_READINESS_TOKEN", "").strip()

# ---------------------------------------------------------------- identity
SYSTEM_NAME_AR = "نظام التحليل الرقابي والموازنة والمصروفات والمشتريات"
SYSTEM_NAME_EN = "Audit Analytics & Budget Control System"
SYSTEM_OWNER = "Abdulhameed — Internal Audit & Financial Review Professional"
SYSTEM_CONTEXT = (
    "Operational financial control system"
    if IS_OPERATIONAL_MODE
    else "Professional Proof-of-Work / Training & Demonstration System"
)
DEMO_NOTICE = (
    ""
    if IS_OPERATIONAL_MODE
    else "بيانات تدريبية Synthetic Training Data — ليست بيانات شركة حقيقية"
)

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
# PostgreSQL only. Web processes use the runtime role; a release/migration task
# opts into its separate connection explicitly and fails closed when absent.
_migration_flag = os.environ.get(
    "DJANGO_USE_MIGRATION_DATABASE", "false"
).strip().lower()
if _migration_flag not in {"true", "false"}:
    raise ImproperlyConfigured(
        "DJANGO_USE_MIGRATION_DATABASE must be 'true' or 'false'."
    )
if _migration_flag == "true":
    DATABASE_URL = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    if not DATABASE_URL:
        raise ImproperlyConfigured(
            "DJANGO_USE_MIGRATION_DATABASE=true requires MIGRATION_DATABASE_URL."
        )
else:
    DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise ImproperlyConfigured(
        "DATABASE_URL is not set. PostgreSQL is mandatory (decision D-01) — "
        "copy .env.example to .env and configure it."
    )
_database_config = dj_database_url.parse(
    DATABASE_URL,
    conn_max_age=600,
    conn_health_checks=True,
    ssl_require=IS_SECURE_ENVIRONMENT,
)
if _database_config.get("ENGINE") != "django.db.backends.postgresql":
    raise ImproperlyConfigured(
        "DATABASE_URL must identify PostgreSQL (SQLite and other engines are unsupported)."
    )
if IS_SECURE_ENVIRONMENT:
    _sslmode = str(
        _database_config.get("OPTIONS", {}).get("sslmode", "require")
    ).lower()
    if _sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ImproperlyConfigured(
            "Staging/production DATABASE_URL must require PostgreSQL TLS."
        )
DATABASES = {"default": _database_config}
SUPABASE_PROJECT_REF = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
SUPABASE_DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL", "").strip()
if SUPABASE_DATABASE_URL:
    _cloud_database_config = dj_database_url.parse(
        SUPABASE_DATABASE_URL,
        conn_max_age=60,
        conn_health_checks=True,
        ssl_require=True,
    )
    if _cloud_database_config.get("ENGINE") != "django.db.backends.postgresql":
        raise ImproperlyConfigured("SUPABASE_DATABASE_URL must identify PostgreSQL.")
    _cloud_database_config.setdefault("OPTIONS", {})["connect_timeout"] = 5
    DATABASES["cloud"] = _cloud_database_config

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
    "django.middleware.locale.LocaleMiddleware",
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
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.system_identity",
            ],
        },
    },
]

# ---------------------------------------------------------------- auth (foundation)
AUTH_USER_MODEL = "accounts.User"

# Self-service registration (email-signup) — open in development, closed in production.
ALLOW_SELF_REGISTRATION = True

AUTHENTICATION_BACKENDS = ["config.backends.EnvironmentModelBackend"]
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
LANGUAGES = [
    ("ar", "العربية"),
    ("en", "English"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
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
if not IS_SECURE_ENVIRONMENT:
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
