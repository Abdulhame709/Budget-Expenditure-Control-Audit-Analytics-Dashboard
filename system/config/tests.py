"""PHASE 2 smoke tests — proves: Django runs, PostgreSQL connects,
migrations apply, and the home page works (real status, no invented data)."""
import django
import os
import secrets
import subprocess
import sys
from pathlib import Path
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.csv_safety import safe_spreadsheet_value


class CsvSafetyTests(TestCase):
    def test_formula_leading_text_and_unicode_markers_are_neutralized(self):
        formula = "=HYPERLINK(\"https://invalid\")"
        self.assertEqual(safe_spreadsheet_value(formula), "'" + formula)
        for prefix in (chr(9), chr(0xFEFF), chr(0x200B)):
            value = prefix + "@SUM(A1:A2)"
            self.assertEqual(safe_spreadsheet_value(value), "'" + value)

    def test_numeric_values_remain_numeric_or_unchanged(self):
        from decimal import Decimal

        self.assertEqual(safe_spreadsheet_value(-12.5), -12.5)
        self.assertEqual(safe_spreadsheet_value(Decimal("-12.50")), Decimal("-12.50"))
        self.assertEqual(safe_spreadsheet_value("-12.50"), "-12.50")
        self.assertEqual(safe_spreadsheet_value(None), "")
        self.assertEqual(safe_spreadsheet_value("ordinary text"), "ordinary text")


class HealthEndpointTests(TestCase):
    def test_liveness_is_public_and_minimal(self):
        response = self.client.get(reverse("health_live"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_is_hidden_without_valid_token(self):
        url = reverse("health_ready")
        self.assertEqual(self.client.get(url).status_code, 404)
        with override_settings(READINESS_CHECK_TOKEN="test-token"):
            self.assertEqual(
                self.client.get(url, HTTP_X_READINESS_TOKEN="wrong").status_code,
                404,
            )

    @override_settings(READINESS_CHECK_TOKEN="test-readiness-token")
    def test_readiness_returns_only_generic_state(self):
        response = self.client.get(
            reverse("health_ready"),
            HTTP_X_READINESS_TOKEN="test-readiness-token",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})
        self.assertNotIn("database", response.content.decode().lower())

    @override_settings(DEPLOYMENT_ENV="production")
    def test_secure_environment_pages_require_authentication(self):
        for url in (reverse("home"), reverse("route_manifest")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("accounts:login"), response.url)


class ProductionDatabaseSelectionTests(SimpleTestCase):
    def test_production_uses_runtime_database_url_for_supabase(self):
        env = os.environ.copy()
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "DJANGO_ENV": "production",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
            "DATABASE_URL": (
                "postgresql://audit:pass@aws-0-example.pooler.supabase.com/audit"
            ),
            "VERCEL": "1",
            "VERCEL_URL": "audit.example.vercel.app",
        })
        env.pop("SUPABASE_DATABASE_URL", None)
        system_dir = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import django; django.setup(); "
                    "from django.conf import settings; "
                    "print(settings.DATABASES['default']['HOST'])"
                ),
            ],
            cwd=system_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("aws-0-example.pooler.supabase.com", result.stdout)


class ProductionConfigTests(TestCase):
    def test_production_settings_reject_wildcard_hosts(self):
        env = os.environ.copy()
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "DJANGO_ENV": "production",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
            "DJANGO_ALLOWED_HOSTS": "*.example.invalid",
            "DATABASE_URL": "postgresql://audit:pass@db.example.invalid/audit",
        })
        system_dir = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "manage.py", "check"],
            cwd=system_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("exact DNS hostnames", result.stdout)

        # Setting DJANGO_ENV=production must not let a base/development
        # settings module silently bypass production security checks.
        env["DJANGO_SETTINGS_MODULE"] = "config.settings.base"
        env["DJANGO_ALLOWED_HOSTS"] = "audit.example.invalid"
        result = subprocess.run(
            [sys.executable, "manage.py", "check"],
            cwd=system_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("must use config.settings.staging or .production", result.stdout)


class DevelopmentConfigTests(TestCase):
    def test_local_http_cookies_work_without_https(self):
        self.assertFalse(settings.CSRF_COOKIE_SECURE)
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")


class Phase2SmokeTests(TestCase):
    def test_django_runs(self):
        self.assertGreaterEqual(django.VERSION[:2], (5, 2))

    def test_postgres_is_the_only_database(self):
        """D-01: PostgreSQL mandatory — never SQLite."""
        self.assertEqual(connection.vendor, "postgresql")
        self.assertNotIn("sqlite", connection.settings_dict["NAME"])
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
        self.assertIn("PostgreSQL", version)

    def test_auth_user_model_foundation(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")

    def test_migrations_apply(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        apps_with_leaves = {app for app, _ in leaves}
        self.assertIn("accounts", apps_with_leaves)
        self.assertIn("governance", apps_with_leaves)
        # nothing pending — every phase's migrations are applied
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        self.assertEqual(plan, [], "unapplied migrations exist")

    def test_user_model_crud(self):
        from apps.accounts.models import User

        user = User.objects.create_user(username="smoke_tester", password="x-Str0ng-pass!")
        self.assertEqual(User.objects.get(pk=user.pk).username, "smoke_tester")

    def test_home_page_renders_with_live_db_status(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نظام التحليل الرقابي")  # system name
        self.assertNotContains(response, "Synthetic Training Data")
        self.assertNotContains(response, "منظومة تدريبية")
        self.assertContains(response, "PostgreSQL محلي")
        self.assertContains(response, "Supabase")
        self.assertIn('dir="rtl"', response.content.decode())

    def test_language_switch_is_available_beside_authenticated_user(self):
        from apps.accounts.models import User

        user = User.objects.create_user(username="language_tester", password="x-Str0ng-pass!")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "English")
        response = self.client.post(reverse("set_language"), {"language": "en", "next": reverse("home")})
        self.assertRedirects(response, reverse("home"))
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'dir="ltr"')
        self.assertContains(response, "Dashboard")

    @override_settings(IS_OPERATIONAL_MODE=True, DEMO_NOTICE="")
    def test_operational_mode_hides_training_banners(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Synthetic Training Data")
        self.assertNotContains(response, "منظومة تدريبية")

    def test_error_pages_render(self):
        from config.views import page_not_found, permission_denied, server_error

        factory = RequestFactory()
        self.assertEqual(page_not_found(factory.get("/missing/")).status_code, 404)
        self.assertEqual(permission_denied(factory.get("/denied/")).status_code, 403)
        self.assertEqual(server_error(factory.get("/boom/")).status_code, 500)
