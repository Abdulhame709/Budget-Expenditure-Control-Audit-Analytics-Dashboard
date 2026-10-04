from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.governance.cloud_sync import (
    _decide_action,
    _find_natural_match,
    _payload_hash,
    _safe_media_path,
    cloud_connection_status,
)


class CloudSyncDecisionTests(SimpleTestCase):
    def test_cloud_new_row_is_added(self):
        self.assertEqual(
            _decide_action(
                local_hash=None,
                cloud_hash="cloud",
                previous_cloud_hash=None,
            ),
            "add",
        )

    def test_cloud_only_change_updates_local(self):
        self.assertEqual(
            _decide_action(
                local_hash="old",
                cloud_hash="new",
                previous_cloud_hash="old",
            ),
            "update",
        )

    def test_local_only_change_is_preserved(self):
        self.assertEqual(
            _decide_action(
                local_hash="local",
                cloud_hash="old",
                previous_cloud_hash="old",
            ),
            "preserve_local",
        )

    def test_both_changed_is_conflict(self):
        self.assertEqual(
            _decide_action(
                local_hash="local",
                cloud_hash="cloud",
                previous_cloud_hash="old",
            ),
            "conflict",
        )

    def test_first_sync_never_overwrites_different_local_row(self):
        self.assertEqual(
            _decide_action(
                local_hash="local",
                cloud_hash="cloud",
                previous_cloud_hash=None,
            ),
            "conflict",
        )

    def test_hash_ignores_primary_key_for_natural_key_matches(self):
        user_model = get_user_model()
        first = user_model(id=1, username="admin", password="same")
        second = user_model(id=99, username="admin", password="same")
        first_values = {field.attname: getattr(first, field.attname) for field in user_model._meta.concrete_fields}
        second_values = {field.attname: getattr(second, field.attname) for field in user_model._meta.concrete_fields}
        self.assertEqual(
            _payload_hash(user_model, first_values),
            _payload_hash(user_model, second_values),
        )

    def test_file_path_cannot_escape_media_root(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                safe = _safe_media_path("imports/2026/report.xlsx")
                self.assertTrue(str(safe).startswith(str(Path(media_root).resolve())))
                with self.assertRaises(ValueError):
                    _safe_media_path("../../outside.txt")

    @override_settings(DEPLOYMENT_ENV="development", DATABASES={"default": {}})
    def test_missing_cloud_alias_has_clear_status(self):
        available, message = cloud_connection_status()
        self.assertFalse(available)
        self.assertIn("SUPABASE_DATABASE_URL", message)


class CloudSyncViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="sync-no-permission",
            password="test-password",
        )
        cls.superuser = get_user_model().objects.create_superuser(
            username="sync-admin",
            password="test-password",
            email="sync@example.com",
        )

    def test_endpoint_requires_settings_permission(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("governance:cloud_sync"))
        self.assertEqual(response.status_code, 403)

    def test_natural_key_match_resolves_different_primary_key(self):
        user_model = get_user_model()
        match = _find_natural_match(
            user_model.objects,
            user_model,
            {"username": self.superuser.username},
        )
        self.assertEqual(match.pk, self.superuser.pk)

    @override_settings(DEPLOYMENT_ENV="production")
    def test_endpoint_is_disabled_in_production(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("governance:cloud_sync"))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_local_page_shows_connection_state(self):
        self.client.force_login(self.superuser)
        with patch(
            "apps.governance.views.cloud_connection_status",
            return_value=(False, "تعذر الاتصال التجريبي"),
        ):
            response = self.client.get(reverse("governance:cloud_sync"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تعذر الاتصال التجريبي")
        self.assertContains(response, "لا تُحذف السجلات المحلية")
