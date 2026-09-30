"""PHASE 3 — real permission tests (not hidden buttons).

Covers: login/logout + password security · page-level URL gating (direct access)
· action-level POST gating · object-level rule (no self role edits) ·
role catalog vs approved matrix · audit trail entries.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import (
    ALL_CODES,
    PERMISSIONS,
    ROLES,
    has_perm,
    user_permission_codes,
)
from apps.accounts.services import create_user, update_user
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


class RoleCatalogTests(TestCase):
    def test_permission_catalog_integrity(self):
        self.assertEqual(len(PERMISSIONS), 30)  # 29 (PHASE 3) + periods.post_closed (PHASE 4)
        self.assertEqual(set(ROLES), {"admin", "auditor", "finance", "management"})
        self.assertEqual(len(ROLES["admin"]["permissions"]), 30)   # everything
        self.assertEqual(len(ROLES["auditor"]["permissions"]), 18)
        self.assertEqual(len(ROLES["finance"]["permissions"]), 12)
        self.assertEqual(len(ROLES["management"]["permissions"]), 5)
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
