"""PHASE 2 smoke tests — proves: Django runs, PostgreSQL connects,
migrations apply, and the home page works (real status, no invented data)."""
import django
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase
from django.urls import reverse


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
        self.assertContains(response, "Synthetic Training Data")  # D-03 label
        self.assertContains(response, "postgresql")  # live DB probe result
        self.assertIn('dir="rtl"', response.content.decode())

    def test_error_pages_render(self):
        from config.views import page_not_found, permission_denied, server_error

        factory = RequestFactory()
        self.assertEqual(page_not_found(factory.get("/missing/")).status_code, 404)
        self.assertEqual(permission_denied(factory.get("/denied/")).status_code, 403)
        self.assertEqual(server_error(factory.get("/boom/")).status_code, 500)
