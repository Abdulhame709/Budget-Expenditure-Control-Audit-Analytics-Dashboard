"""PHASE 5 — Budget Management: calculations, constraints, workflow, perms.

Proves: annual = Σ(months) (clean + DB CHECK), non-negative, unique line
per (version, dept, account), expense accounts only, category inheritance,
one budget per FY, draft⇄approved workflow with audit, approved-version
lock (revision flow), DB-computed totals & the analysis-version selector,
budget.view/budget.edit gating over real HTTP, and the Budget-vs-Actual /
Variance / Out-of-Budget FOUNDATION (monthly_budget_map, is_budgeted).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.governance.models import AuditLog
from apps.budget import services
from apps.budget.models import Budget, BudgetLine, BudgetVersion, MONTH_FIELDS
from apps.reference.models import Account, Department, ExpenseCategory, FiscalYear

User = get_user_model()
PW = "S3cure-Demo-Pass!"
D = Decimal


def make_user(username, role_code):
    user = User.objects.create_user(username=username, password=PW)
    UserRole.objects.create(user=user, role=Role.objects.get(code=role_code))
    return user


def make_fy(code="FY2026", year=2026):
    return FiscalYear.objects.create(
        code=code, name=f"السنة {year}", year=year,
        start_date=date(year, 1, 1), end_date=date(year, 12, 31),
    )


def make_budget(fy, name="ميزانية تجريبية"):
    return Budget.objects.create(fiscal_year=fy, name=name)


def make_version(budget, version=1, status="draft"):
    return BudgetVersion.objects.create(
        budget=budget, version=version, status=status)


def base_objects():
    dept = Department.objects.create(code="OPS1", name="العمليات")
    cat = ExpenseCategory.objects.create(code="TRV", name="تنقّل")
    acc = Account.objects.create(code="5101", name="مصروفات تنقّل",
                                 account_type="expense", expense_category=cat)
    asset = Account.objects.create(code="1100", name="نقدية",
                                   account_type="asset")
    return dept, cat, acc, asset


def make_line(version, dept, acc, months=None, **extra):
    months = months or {}
    values = {f: months.get(f, 0) for f in MONTH_FIELDS}
    line = BudgetLine(version=version, department=dept, account=acc,
                      **values, **extra)
    line.full_clean()   # derives annual_amount (as the views do) before save
    line.save()
    return line


# ================================================================ calculations
class BudgetLineCalculationTests(TestCase):
    def setUp(self):
        self.fy = make_fy()
        self.budget = make_budget(self.fy)
        self.version = make_version(self.budget)
        self.dept, self.cat, self.acc, self.asset = base_objects()

    def test_annual_is_derived_from_months(self):
        line = BudgetLine(
            version=self.version, department=self.dept, account=self.acc,
            m01=D("1000.50"), m02=D("2000.25"), m06=D("500.00"),
        )
        line.full_clean()
        self.assertEqual(line.annual_amount, D("3500.75"))
        self.assertEqual(line.expense_category_id, self.cat.pk)  # inherited

    def test_db_check_rejects_mismatched_annual(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BudgetLine.objects.create(
                    version=self.version, department=self.dept, account=self.acc,
                    m01=D("100"), annual_amount=D("999"),
                )

    def test_db_check_allows_correct_sum(self):
        line = make_line(self.version, self.dept, self.acc,
                         {"m01": D("100"), "m03": D("50")})
        self.assertEqual(line.annual_amount, D("150"))

    def test_negative_month_rejected(self):
        line = BudgetLine(
            version=self.version, department=self.dept, account=self.acc,
            m01=D("-1"),
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_non_expense_account_rejected(self):
        line = BudgetLine(
            version=self.version, department=self.dept, account=self.asset,
            m01=D("10"),
        )
        with self.assertRaises(ValidationError) as ctx:
            line.full_clean()
        self.assertIn("account", ctx.exception.error_dict)

    def test_unique_line_per_version_dept_account(self):
        make_line(self.version, self.dept, self.acc, {"m01": D("10")})
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # bypass full_clean to prove the DB-level constraint
                BudgetLine.objects.create(
                    version=self.version, department=self.dept, account=self.acc,
                    m01=D("20"), annual_amount=D("20"),
                )

    def test_one_budget_per_fiscal_year(self):
        with self.assertRaises(ValidationError) as ctx:
            Budget(fiscal_year=self.fy, name="أخرى").full_clean()
        self.assertIn("fiscal_year", ctx.exception.error_dict)


# ================================================================ workflow
class BudgetWorkflowTests(TestCase):
    def setUp(self):
        self.fy = make_fy()
        self.budget = make_budget(self.fy)
        self.version = make_version(self.budget)
        self.dept, self.cat, self.acc, _ = base_objects()
        make_line(self.version, self.dept, self.acc, {"m01": D("1000")})
        self.admin = make_user("adm_b5", "admin")

    def test_analysis_version_none_until_approved(self):
        self.assertIsNone(services.get_analysis_version(self.budget))
        self.version.status = "approved"
        self.version.save()
        analysis = services.get_analysis_version(self.budget)
        self.assertEqual(analysis.pk, self.version.pk)

    def test_latest_approved_wins_for_analysis(self):
        v2 = make_version(self.budget, version=2, status="approved")
        analysis = services.get_analysis_version(self.budget)
        self.assertEqual(analysis.pk, v2.pk)  # revised budget becomes THE one
        self.assertTrue(BudgetVersion.objects.get(pk=v2.pk).is_analysis_version)
        self.assertFalse(
            BudgetVersion.objects.get(pk=self.version.pk).is_analysis_version)


class VersionTotalsServiceTests(TestCase):
    """The numbers analysis will use — straight from DB aggregates."""

    def setUp(self):
        self.fy = make_fy()
        self.budget = make_budget(self.fy)
        self.v = make_version(self.budget)
        self.dept, self.cat, self.acc, _ = base_objects()
        self.dept2 = Department.objects.create(code="FIN1", name="المالية")
        self.acc2 = Account.objects.create(code="5102", name="مستلزمات",
                                           account_type="expense")
        make_line(self.v, self.dept, self.acc,
                  {"m01": D("100"), "m02": D("200")})
        make_line(self.v, self.dept, self.acc2, {"m03": D("50")})
        make_line(self.v, self.dept2, self.acc, {"m01": D("400")})

    def test_version_totals(self):
        totals = services.version_totals(self.v)
        self.assertEqual(totals["annual_total"], D("750"))
        self.assertEqual(totals["monthly"][0], D("500"))   # 100 + 400
        self.assertEqual(totals["monthly"][2], D("50"))
        self.assertEqual(totals["monthly"][3], D("0"))
        self.assertEqual(totals["line_count"], 3)

    def test_totals_by_department_and_account(self):
        by_dept = services.totals_by(self.v, "department")
        self.assertEqual(
            {r["key"]: r["total"] for r in by_dept},
            {self.dept.pk: D("350"), self.dept2.pk: D("400")},
        )
        by_acc = services.totals_by(self.v, "account")
        self.assertEqual(
            {r["key"]: r["total"] for r in by_acc},
            {self.acc.pk: D("700"), self.acc2.pk: D("50")},
        )

    def test_monthly_budget_map_foundation(self):
        m = services.monthly_budget_map(self.v)
        key = (self.dept.pk, self.acc.pk)
        self.assertIn(key, m)
        self.assertEqual(m[key]["monthly"][0], D("100"))
        self.assertEqual(m[key]["annual"], D("300"))

    def test_is_budgeted_foundation_oob(self):
        # covered pair
        self.assertTrue(services.is_budgeted(self.v, self.dept, self.acc))
        # another dept using the same account → NOT budgeted (OOB candidate)
        dept3 = Department.objects.create(code="X9", name="غير ممولة")
        self.assertFalse(services.is_budgeted(self.v, dept3, self.acc))
        self.assertIsNone(services.line_for(self.v, dept3, self.acc))


# ================================================================ HTTP + perms
class BudgetHttpTests(TestCase):
    def setUp(self):
        self.fy = make_fy()
        self.budget = make_budget(self.fy)
        self.version = make_version(self.budget)
        self.dept, self.cat, self.acc, _ = base_objects()
        make_line(self.version, self.dept, self.acc, {"m01": D("1000")})
        self.admin = make_user("adm_http5", "admin")
        self.finance = make_user("fin_http5", "finance")
        self.auditor = make_user("aud_http5", "auditor")
        self.mgmt = make_user("mgmt_http5", "management")

    def _client(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("budget:budget_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_management_denied_budget_pages(self):
        # management has no budget.view in the approved Phase-3 matrix
        c = self._client(self.mgmt)
        self.assertEqual(c.get(reverse("budget:budget_list")).status_code, 403)
        self.assertEqual(
            c.get(reverse("budget:version_detail", args=[self.version.pk])).status_code,
            403)

    def test_auditor_views_but_cannot_mutate(self):
        c = self._client(self.auditor)
        self.assertEqual(c.get(reverse("budget:budget_list")).status_code, 200)
        self.assertEqual(
            c.get(reverse("budget:version_detail", args=[self.version.pk])).status_code,
            200)
        self.assertEqual(
            c.get(reverse("budget:line_create", args=[self.version.pk])).status_code,
            403)
        self.assertEqual(
            c.post(reverse("budget:version_approve", args=[self.version.pk])).status_code,
            403)

    def test_finance_creates_budget_with_version1(self):
        c = self._client(self.finance)
        fy27 = make_fy(code="FY2027", year=2027)
        response = c.post(reverse("budget:budget_create"), {
            "fiscal_year": fy27.pk, "name": "ميزانية المالية", "notes": "",
        })
        self.assertEqual(response.status_code, 302)
        budget = Budget.objects.get(name="ميزانية المالية")
        v1 = budget.versions.get()
        self.assertEqual(v1.version, 1)
        self.assertEqual(v1.status, "draft")
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="budget",
            entity_id=str(budget.pk)).exists())
        self.assertTrue(AuditLog.objects.filter(
            action="budget_version_created",
            entity_id=str(v1.pk)).exists())

    def test_finance_adds_line_total_derived(self):
        c = self._client(self.finance)
        dept2 = Department.objects.create(code="FIN1", name="المالية")
        response = c.post(
            reverse("budget:line_create", args=[self.version.pk]),
            {"department": dept2.pk, "account": self.acc.pk,
             "expense_category": "", "notes": "",
             "m01": "1500", "m06": "500"},
        )
        self.assertEqual(response.status_code, 302)
        line = BudgetLine.objects.get(version=self.version,
                                      department=dept2, account=self.acc)
        self.assertEqual(line.annual_amount, D("2000"))
        self.assertTrue(AuditLog.objects.filter(
            action="entity_created", entity_type="budgetline",
            entity_id=str(line.pk)).exists())

    def test_admin_approves_locks_and_audits(self):
        c = self._client(self.admin)
        response = c.post(reverse("budget:version_approve",
                                  args=[self.version.pk]))
        self.assertEqual(response.status_code, 302)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "approved")
        self.assertEqual(self.version.approved_by_id, self.admin.pk)
        entry = AuditLog.objects.filter(action="budget_approved",
                                        entity_id=str(self.version.pk)).first()
        self.assertIsNotNone(entry)
        self.assertIn("1000", entry.diff.get("annual_total", ""))

    def test_approved_version_rejects_line_edits_403(self):
        self.version.status = "approved"
        self.version.save()
        c = self._client(self.admin)
        line = self.version.lines.first()
        # GET edit form → 403 (locked)
        response = c.get(reverse("budget:line_edit", args=[line.pk]))
        self.assertEqual(response.status_code, 403)
        # POST delete → 403 as well
        response = c.post(reverse("budget:line_delete", args=[line.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(BudgetLine.objects.filter(pk=line.pk).exists())

    def test_unapprove_reopens_with_audit(self):
        self.version.status = "approved"
        self.version.save()
        c = self._client(self.admin)
        c.post(reverse("budget:version_unapprove", args=[self.version.pk]))
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "draft")
        self.assertIsNone(self.version.approved_by)
        self.assertTrue(AuditLog.objects.filter(
            action="budget_unapproved",
            entity_id=str(self.version.pk)).exists())

    def test_new_revision_copies_lines_and_becomes_analysis_after_approval(self):
        c = self._client(self.admin)
        # approve v1 first → analysis = v1
        c.post(reverse("budget:version_approve", args=[self.version.pk]))
        self.assertEqual(services.get_analysis_version(self.budget).version, 1)
        # create revision
        response = c.post(reverse("budget:version_new_revision",
                                  args=[self.budget.pk]))
        self.assertEqual(response.status_code, 302)
        v2 = self.budget.versions.get(version=2)
        self.assertEqual(v2.status, "draft")
        self.assertEqual(v2.lines.count(), 1)
        self.assertEqual(v2.lines.first().annual_amount, D("1000"))
        # analysis still v1 (approved) until v2 approved
        self.assertEqual(services.get_analysis_version(self.budget).version, 1)
        c.post(reverse("budget:version_approve", args=[v2.pk]))
        self.assertEqual(services.get_analysis_version(self.budget).version, 2)
        self.assertTrue(AuditLog.objects.filter(
            action="budget_version_created",
            entity_id=str(v2.pk)).exists())

    def test_cannot_delete_budget_with_approved_version(self):
        self.version.status = "approved"
        self.version.save()
        c = self._client(self.admin)
        response = c.post(reverse("budget:budget_delete", args=[self.budget.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Budget.objects.filter(pk=self.budget.pk).exists())

    def test_can_delete_draft_only_budget_with_audit(self):
        c = self._client(self.admin)
        pk = self.budget.pk
        response = c.post(reverse("budget:budget_delete", args=[pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Budget.objects.filter(pk=pk).exists())
        self.assertTrue(AuditLog.objects.filter(
            action="entity_deleted", entity_type="budget",
            entity_id=str(pk)).exists())

    def test_approve_empty_version_refused(self):
        empty = make_version(self.budget, version=7)
        c = self._client(self.admin)
        response = c.post(reverse("budget:version_approve", args=[empty.pk]))
        self.assertEqual(response.status_code, 302)  # redirect back
        empty.refresh_from_db()
        self.assertEqual(empty.status, "draft")  # NOT approved

    def test_summary_page_shows_db_totals(self):
        c = self._client(self.admin)
        response = c.get(reverse("budget:version_summary",
                                 args=[self.version.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1000")          # annual total
        self.assertContains(response, "النسخة المستخدمة في التحليل")

    def test_list_search_and_status_filter(self):
        fy25 = make_fy(code="FY2025", year=2025)
        old = make_budget(fy25, name="ميزانية السنة القديمة")
        make_version(old)  # draft version
        c = self._client(self.admin)
        url = reverse("budget:budget_list")
        self.assertEqual(c.get(url, {"q": "قديمة"}).context["total"], 1)
        self.assertEqual(c.get(url, {"q": "FIN"}).context["total"], 0)
        # status filter: budget whose version is draft
        self.assertEqual(c.get(url, {"status": "draft"}).context["total"], 2)
        self.assertEqual(c.get(url, {"status": "approved"}).context["total"], 0)
