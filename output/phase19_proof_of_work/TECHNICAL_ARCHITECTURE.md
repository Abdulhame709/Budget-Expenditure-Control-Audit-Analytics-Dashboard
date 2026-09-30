# Technical Architecture Summary

### Budget & Expenditure Control — Audit Analytics System
*System Architecture, Data Pipelines, and Security Controls*

---

## 1. System Topology & Stack
- **Framework**: Django 5.2 LTS (Python 3.11).
- **Database Engine**: PostgreSQL 16 (D-01: strict PostgreSQL mandate, no SQLite fallback).
- **Database Driver**: `psycopg 3.3` with connection health checks and pooled connections (`conn_max_age=600`).
- **Application Server (WSGI)**: Gunicorn 26.2 (multi-worker synchronization).
- **Static Asset Delivery**: WhiteNoise 6.12 with `CompressedManifestStaticFilesStorage`.
- **Frontend Architecture**: Localized Bootstrap 5.3.3 RTL, custom print CSS, and Chart.js 4 (fully self-contained in `system/static/vendor/` with zero external CDN dependencies).

---

## 2. Modular Application Structure
The application code is partitioned into 10 decoupled local apps under `system/apps/`:

| App | Primary Responsibility | Key Entities / Services |
|:---|:---|:---|
| `config` | Core settings, routing, WSGI/ASGI, error handlers (403, 404, 500). | Settings split (`base`, `dev`, `prod`), fail-fast validators. |
| `accounts` | Custom user model, RBAC enforcement, session management. | `User`, `Role`, `Permission`, `UserRole`, `AccessControlMiddleware` (30 permissions). |
| `reference` | Organizational master data and accounting foundations. | `Department`, `Account`, `ExpenseCategory`, `Supplier`, `FiscalYear`, `MonthlyPeriod`. |
| `budget` | Budgetary limits, monthly distributions, and version approvals. | `Budget`, `BudgetVersion`, `BudgetLine` (DB constraint: $\text{Annual} = \sum m01..m12$). |
| `expenses` | Actual expenditure recording, invoice validations, and document status. | `Expense` (Rule: $\le 500\text{K}$ limit, unapproved flagging, closed period check). |
| `procurement` | Purchase requisitions, mandatory 3-quote validation, POs, and receipts. | `Procurement`, `Quotation`, `PurchaseOrder`, `GoodsReceipt`. |
| `imports` | File ingestion, tabular extraction, row validation, and atomic commits. | `ImportJob`, `ImportRowError`, CSV/XLSX/PDF pipeline services. |
| `audit_register` | Core analytics engine: 14 evaluators, risk engine, findings workflow. | `AuditTest`, `AuditRun`, `AuditException`, `AuditFinding`, test evaluators. |
| `analytics` | High-level KPI aggregations and multi-filter visual dashboards. | `DashboardView`, dynamic query builders, Chart.js payload serializers. |
| `reports` | 9 audit-grade reports with multi-format export capability. | Report builders, HTML + Print CSS, CSV (UTF-8 BOM), and openpyxl XLSX. |
| `governance` | Immutable audit logging, entity diff snapshots, and general attachments. | `AuditLog`, `Attachment`, generic relations (`content_type`). |

---

## 3. The 14 Audit Test Evaluators
The audit engine executes 14 automated evaluators parameterizable via database thresholds:
1. `T-BUD-01`: Budget Overrun (Annual actual spend > approved annual budget).
2. `T-BUD-02`: Budget Variance Spike (Monthly expenditure variance > threshold percentage).
3. `T-BUD-03`: Out-of-Budget Spending (Expenditures charged without an approved budget line).
4. `T-EXP-01`: Missing Supporting Documentation (Expenses marked without verified receipt/invoice).
5. `T-EXP-02`: Unapproved Expenditure (Actual expenses executed without managerial approval).
6. `T-EXP-03`: High-Value Cash Transaction (Cash payments exceeding single-transaction threshold).
7. `T-EXP-04`: Duplicate Invoices (Identical supplier, invoice number, or matching date/amount).
8. `T-EXP-05`: Unusual Transaction Amount (Single expenses exceeding statistical thresholds).
9. `T-EXP-06`: Inappropriate Account Classification (Expenses miscoded against incompatible categories).
10. `T-EXP-07`: Split Transactions / Threshold Circumvention (Multiple payments just under approval limits).
11. `T-PRC-01`: Missing Purchase Order (Procurement activities without verified PO reference).
12. `T-PRC-02`: Insufficient Quotations (Procurement orders lacking mandatory 3 supplier quotes).
13. `T-PRC-03`: Inactive / Unregistered Supplier (Transactions associated with inactive vendors).
14. `T-PRC-04`: Goods Receipt Discrepancy (Discrepancies between PO quantity/amount and GRN receipt).

---

## 4. Security & Governance Architecture
- **Fail-Fast Configuration**: `production.py` immediately halts startup if `DJANGO_SECRET_KEY` is missing, short (< 50 chars), or contains placeholder text.
- **Granular RBAC**: 30 discrete permission codes evaluated by `AccessControlMiddleware` and view decorators.
- **Audit Logging**: Sensitive events capture actor, action, timestamp, client IP, user agent, and JSON diffs of changed fields.
- **Database Hardening**: No SQLite in production; strict foreign keys, unique constraints, and PostgreSQL check constraints.
