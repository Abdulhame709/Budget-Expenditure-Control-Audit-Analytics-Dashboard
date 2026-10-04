"""PHASE 3 — real permission tests (not hidden buttons).

Covers: login/logout + password security · page-level URL gating (direct access)
· action-level POST gating · object-level rule (no self role edits) ·
role catalog vs approved matrix · audit trail entries.
"""
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import (
    ALL_CODES,
    PERMISSIONS,
    ROLES,
    has_perm,
    user_permission_codes,
)
from apps.accounts.services import create_user, register_user, update_user
from apps.governance.models import AuditLog

User = get_user_model()

PW = "S3cure-Demo-Pass!"  # satisfies Django validators


def make_user(username: str, role_code: str | None, password: str = PW):
    user = User.objects.create_user(username=username, password=password)
    if role_code:
        UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


class AuthFlowTests(TestCase):
    def test_anonymous_direct_url_redirects_to_login(self):
        """Page-level: typing the URL directly must NOT bypass permissions."""
        response = self.client.get(reverse("accounts:users_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertIn("next=", response.url)

    def test_public_pages_still_open(self):
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)

    def test_login_wrong_password_fails_and_is_logged(self):
        make_user("alice_finance", "finance")
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "alice_finance", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)  # re-render with error
        self.assertContains(response, "غير صحيحة")
        self.assertTrue(
            AuditLog.objects.filter(action="login_failed",
                                    entity_id="alice_finance").exists()
        )

    def test_login_success_creates_audit_entry(self):
        make_user("bob_auditor", "auditor")
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "bob_auditor", "password": PW},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        entry = AuditLog.objects.filter(action="login", actor__username="bob_auditor").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.action, "login")

    def test_logout_requires_post_and_logs(self):
        user = make_user("carol_mgmt", "management")
        self.client.force_login(user)
        # GET logout should not log out (POST-only view)
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AuditLog.objects.filter(action="logout",
                                                actor__username="carol_mgmt").exists())

    def test_password_never_stored_in_plaintext(self):
        user = make_user("dave_admin", "admin")
        self.assertNotEqual(user.password, PW)
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertNotIn(PW, user.password)

    def test_password_change_requires_login(self):
        response = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_password_change_rejects_wrong_current_password(self):
        user = make_user("self_rotate_invalid", "finance")
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "incorrect",
                "new_password1": "N3w-Secure-Password!",
                "new_password2": "N3w-Secure-Password!",
            },
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PW))

    def test_password_change_keeps_session_and_writes_safe_audit_log(self):
        user = make_user("self_rotate", "finance")
        self.client.force_login(user)
        new_password = "N3w-Secure-Password!"
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": PW,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
        log = AuditLog.objects.get(action="password_changed", entity_id=str(user.pk))
        self.assertEqual(log.diff, {"result": "changed", "scope": "self"})
        self.assertNotIn(new_password, str(log.diff))


class RoleCatalogTests(TestCase):
    def test_permission_catalog_integrity(self):
        self.assertEqual(len(PERMISSIONS), 30)  # 29 (PHASE 3) + periods.post_closed (PHASE 4)
        self.assertEqual(
            set(ROLES), {"admin", "auditor", "finance", "management", "viewer"}
        )
        self.assertEqual(len(ROLES["admin"]["permissions"]), 30)   # everything
        self.assertEqual(len(ROLES["auditor"]["permissions"]), 18)
        self.assertEqual(len(ROLES["finance"]["permissions"]), 12)
        self.assertEqual(len(ROLES["management"]["permissions"]), 5)
        self.assertEqual(len(ROLES["viewer"]["permissions"]), 12)
        for spec in ROLES.values():
            for code in spec["permissions"]:
                self.assertIn(code, ALL_CODES)

    def test_admin_role_has_everything(self):
        admin = make_user("root_admin", "admin")
        self.assertEqual(user_permission_codes(admin), ALL_CODES)

    def test_management_is_read_only(self):
        mgmt = make_user("viewer", "management")
        # read allowed
        for code in ("dashboard.view", "reports.view", "findings.view",
                     "risk.view", "exceptions.view"):
            self.assertTrue(has_perm(mgmt, code), code)
        # no modification anywhere
        for code in ("budget.edit", "expenses.edit", "procurement.edit",
                     "exceptions.manage", "findings.manage", "audit.run",
                     "users.manage", "imports.run"):
            self.assertFalse(has_perm(mgmt, code), code)

    def test_project_viewer_has_project_wide_read_only_access(self):
        viewer = make_user("project_viewer", "viewer")
        for code in (
            "dashboard.view", "reference.view", "budget.view", "expenses.view",
            "procurement.view", "imports.view", "audit.view", "exceptions.view",
            "risk.view", "findings.view", "reports.view", "attachments.view",
        ):
            self.assertTrue(has_perm(viewer, code), code)
        for code in (
            "budget.edit", "expenses.edit", "procurement.edit", "imports.run",
            "audit.run", "findings.manage", "users.manage",
        ):
            self.assertFalse(has_perm(viewer, code), code)

    def test_self_registration_assigns_project_viewer_role(self):
        user = register_user(
            email="new.viewer@example.com",
            password=PW,
            full_name="مستخدم مستعرض",
        )
        self.assertEqual(
            list(UserRole.objects.filter(user=user).values_list(
                "role__code", flat=True
            )),
            ["viewer"],
        )
        self.assertTrue(has_perm(user, "budget.view"))
        self.assertFalse(has_perm(user, "budget.edit"))

    def test_finance_scope(self):
        fin = make_user("fin_user", "finance")
        for code in ("budget.edit", "expenses.edit", "procurement.edit", "imports.run"):
            self.assertTrue(has_perm(fin, code), code)
        for code in ("audit.run", "audit.rules.manage", "findings.manage",
                     "users.manage", "exceptions.manage"):
            self.assertFalse(has_perm(fin, code), code)

    def test_auditor_scope(self):
        aud = make_user("aud_user", "auditor")
        for code in ("audit.run", "audit.rules.manage", "exceptions.manage",
                     "findings.manage", "audittrail.view", "reports.generate"):
            self.assertTrue(has_perm(aud, code), code)
        self.assertFalse(has_perm(aud, "budget.edit"))
        self.assertFalse(has_perm(aud, "users.manage"))


class PageLevelAccessTests(TestCase):
    def setUp(self):
        self.admin = make_user("adm", "admin")
        self.auditor = make_user("aud", "auditor")
        self.finance = make_user("fin", "finance")
        self.mgmt = make_user("mgmt", "management")

    def _login(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_admin_can_open_user_management(self):
        self.assertEqual(self._login(self.admin).get(
            reverse("accounts:users_list")).status_code, 200)
        self.assertEqual(self._login(self.admin).get(
            reverse("accounts:roles_list")).status_code, 200)

    def test_direct_url_403_by_role(self):
        cases = [
            ("accounts:users_list", ["auditor", "finance", "management"]),
            ("accounts:user_create", ["auditor", "finance", "management"]),
            ("accounts:roles_list", ["auditor", "finance", "management"]),
            ("governance:audit_trail", ["finance", "management"]),
        ]
        for url_name, denied_roles in cases:
            for role in denied_roles:
                response = self._login(getattr(self, {"auditor": "auditor",
                                                      "finance": "finance",
                                                      "management": "mgmt"}[role])).get(
                    reverse(url_name))
                self.assertEqual(
                    response.status_code, 403,
                    f"{role} must be denied on {url_name} (got {response.status_code})",
                )

    def test_auditor_can_open_audit_trail(self):
        self.assertEqual(self._login(self.auditor).get(
            reverse("governance:audit_trail")).status_code, 200)


class ActionLevelTests(TestCase):
    def test_post_user_create_denied_for_non_admin(self):
        finance = make_user("fin2", "finance")
        client = Client()
        client.force_login(finance)
        response = client.post(
            reverse("accounts:user_create"),
            {"username": "hacker", "password1": PW, "password2": PW},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="hacker").exists())

    def test_admin_creates_user_and_audit_diffs(self):
        admin = make_user("adm2", "admin")
        client = Client()
        client.force_login(admin)
        response = client.post(
            reverse("accounts:user_create"),
            {
                "username": "new_auditor",
                "password1": PW,
                "password2": PW,
                "full_name": "مدقق جديد",
                "roles": [Role.objects.get(code="auditor").pk],  # field needs PKs
            },
        )
        self.assertEqual(response.status_code, 302)
        created = User.objects.get(username="new_auditor")
        self.assertTrue(created.check_password(PW))
        self.assertEqual(list(
            UserRole.objects.filter(user=created).values_list("role__code", flat=True)
        ), ["auditor"])
        log = AuditLog.objects.filter(action="user_created",
                                      entity_id=str(created.pk)).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.diff.get("roles"), ["auditor"])
        self.assertNotIn("password", str(log.diff).lower())

    def test_admin_can_reset_another_users_password(self):
        admin = make_user("password_admin", "admin")
        target = make_user("password_target", "finance")
        client = Client()
        client.force_login(admin)
        new_password = "An0ther-Secure-Password!"
        response = client.post(
            reverse("accounts:user_password_reset", args=[target.pk]),
            {"new_password1": new_password, "new_password2": new_password},
        )
        self.assertRedirects(response, reverse("accounts:user_detail", args=[target.pk]))
        target.refresh_from_db()
        self.assertTrue(target.check_password(new_password))
        log = AuditLog.objects.get(action="password_changed", entity_id=str(target.pk))
        self.assertEqual(log.actor, admin)
        self.assertEqual(log.diff["scope"], "administrator_reset")
        self.assertNotIn(new_password, str(log.diff))

    def test_non_admin_cannot_open_user_password_reset(self):
        finance = make_user("password_finance", "finance")
        target = make_user("password_other", "auditor")
        client = Client()
        client.force_login(finance)
        response = client.get(reverse("accounts:user_password_reset", args=[target.pk]))
        self.assertEqual(response.status_code, 403)


class ObjectLevelTests(TestCase):
    def test_admin_cannot_change_own_roles(self):
        admin = make_user("adm3", "admin")
        with self.assertRaises(PermissionDenied):
            update_user(
                actor=admin, target=admin, role_codes=["management"],
            )
        # roles unchanged
        self.assertEqual(list(
            UserRole.objects.filter(user=admin).values_list("role__code", flat=True)
        ), ["admin"])

    def test_admin_cannot_edit_own_record_via_url(self):
        admin = make_user("adm4", "admin")
        client = Client()
        client.force_login(admin)
        response = client.post(
            reverse("accounts:user_detail", args=[admin.pk]),
            {"full_name": "X", "job_title": "Y", "is_active": True,
             "is_demo": False,
             "roles": [Role.objects.get(code="management").pk]},
        )
        self.assertEqual(response.status_code, 403)

    def test_roles_change_logged_with_before_after(self):
        admin = make_user("adm5", "admin")
        target = make_user("fin3", "finance")
        update_user(actor=admin, target=target, role_codes=["management"])
        log = AuditLog.objects.filter(action="roles_changed",
                                      entity_id=str(target.pk)).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.diff["before"], ["finance"])
        self.assertEqual(log.diff["after"], ["management"])


class LoginRequiredObjectTests(TestCase):
    def test_profile_requires_login_and_shows_own_scope_only(self):
        user = make_user("own_user", "finance")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)  # anonymous → login
        client = Client()
        client.force_login(user)
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "own_user")
        self.assertContains(response, "budget.edit")
        self.assertNotContains(response, "users.manage")  # not this user's perm


class ProductionDemoGuardTests(TestCase):
    @override_settings(DEPLOYMENT_ENV="production")
    def test_demo_accounts_cannot_authenticate(self):
        demo = User.objects.create_user(
            username="tagged_demo", password=PW, is_demo=True)
        self.assertIsNone(authenticate(username="tagged_demo", password=PW))
        self.assertTrue(demo.is_demo)

    @override_settings(DEPLOYMENT_ENV="production")
    def test_demo_accounts_cannot_be_created_or_reclassified(self):
        from django.core.exceptions import ValidationError

        admin = make_user("production_admin_guard", "admin")
        with self.assertRaises(ValidationError):
            create_user(
                actor=admin, username="blocked_demo", password=PW,
                role_codes=["finance"], is_demo=True)
        demo = User.objects.create_user(
            username="existing_demo_guard", password=PW, is_demo=True)
        with self.assertRaises(ValidationError):
            update_user(actor=admin, target=demo, is_demo=False)
