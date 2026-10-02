# Project Proof — Budget & Expenditure Control Audit Analytics System

| Element | Specification |
|:---|:---|
| **PROJECT** | Budget & Expenditure Control — Audit Analytics System |
| **ARABIC TITLE** | لوحة ونظام تحليل الموازنة والمصروفات والمشتريات والاستثناءات الرقابية |
| **OWNER** | **Abdulhameed** — Project Author & Creator |
| **ROLE** | **Internal Audit & Financial Review Professional / System Designer** |
| **CONTEXT** | **Professional Proof-of-Work / Independent Training & Demonstration System** |
| **DATASET** | **100% Synthetic Training Data** (FY2026 model dataset — no real employer or client data) |
| **STATUS** | Production qualification in progress (not deployment approval) · Local PostgreSQL suite 353/353 · Manus demo URL responded 2026-10-02; deployed revision/provider configuration not verified |

---

## 1. PROBLEM
In conventional financial review settings, internal audit and control functions struggle with:
- **Disconnected Data Sources**: Expenditure and procurement data isolated in disjointed spreadsheets or ERP exports.
- **Manual & Subjective Sampling**: Inability to test 100% of transactions, resulting in undetected out-of-budget spending, unapproved expenditures, and quotation policy bypasses.
- **Lack of Objective Risk Scoring**: Inconsistent classification of control exceptions (High, Medium, Low) and lack of standardized root-cause tracking.
- **Weak Audit Trails**: Absence of immutable, verifiable change histories when financial records or audit rules are modified.

---

## 2. OWNER
- **Author & Owner**: **Abdulhameed**
- **Professional Identity**: Internal Audit & Financial Review Professional / System Designer.
- **Independence**: This system is an independent professional portfolio project developed to demonstrate domain mastery in audit analytics, control design, and technical system architecture. It does not represent any current or former employer, client, or real commercial entity.

---

## 3. SOLUTION
A database-backed, audit analytics and financial expenditure control web system engineered with:
- **Full Relational Data Model**: PostgreSQL database enforcing strict referential integrity across 10 functional modules (Chart of Accounts, Departments, Fiscal Periods, Approved Budgets, Actual Expenses, Procurement, Audit Register, Analytics, Reports, and Governance).
- **Extensible Audit Engine**: 14 automated control evaluators running against complete transaction populations (budget overruns, variance spikes, unapproved expenses, split purchases, single-source procurement, and duplicate payments).
- **Three-Tier Risk & Exception Workflow**: Automated risk scoring (High / Medium / Low) with full lifecycle handling (`open` → `acknowledged` → `resolved`) and actionable management findings/recommendations.
- **Multi-Format Ingestion**: Three-stage validation pipeline for Excel, CSV, and PDF extraction with atomic commit guards.
- **Auditor-First UX**: Responsive RTL Arabic interface (Bootstrap 5.3 RTL + Chart.js) with interactive KPI dashboards, 9 exportable reports (HTML, Print CSS, UTF-8 BOM CSV, and XLSX), and general attachment handling.

---

## 4. ROLE
**Internal Audit & Financial Review Professional / System Designer**:
- Designed the internal control framework, exception definitions, and mathematical variance models.
- Formalized the 14 audit test evaluators and calibrated detection thresholds against synthetic policy criteria.
- Architected the 30-permission role-based access control (RBAC) matrix across four standard roles (`admin`, `auditor`, `finance`, `management`).
- Authored the comprehensive synthetic dataset and predefined the 28 ground-truth control exceptions.
- The current local test automation suite passes 353 tests; this is local evidence, not provider verification.

---

## 5. TOOLS
- **Core Framework**: Django 5.2 LTS (Python 3.11).
- **Database Engine**: PostgreSQL 16 (strict rule D-01: genuine PostgreSQL, no SQLite).
- **Database Driver**: `psycopg 3` + `dj-database-url`.
- **WSGI & Server**: Gunicorn + WhiteNoise (Compressed Manifest Static Storage).
- **Data Ingestion & Processing**: `pandas`, `openpyxl`, `pdfplumber`.
- **Frontend & Visualization**: Bootstrap 5.3.3 RTL (self-contained vendor assets), Chart.js 4 (client-side dynamic charts), custom CSS with print stylesheets.
- **Version Control & CI/CD**: Git + GitHub CLI (`gh`), `render.yaml` deployment blueprints.

---

## 6. EVIDENCE
1. **Source Code**: Fully documented Git repository with clean separation of code, migrations, and audit seeds.
2. **Automated Test Suite**: 353 passing local tests (299 unit/integration tests + 54 synthetic dataset/ground-truth tests); provider behavior remains unverified.
3. **Ground Truth Verification**: Exact match against 28 Ground-Truth Control Exceptions in `apps.audit_register.tests_dataset` (zero false positives against the predefined Ground-Truth test set; zero false negatives within that test set).
4. **Data Integrity & Checksums**: 7 published evidence artifacts verified with SHA-256 (`sha256sum -c evidence/checksums.txt` = 7/7 OK).
5. **Manus Demo endpoint**: the previously shared URL returned the demo page during a read-only check on 2026-10-02. The served revision and provider configuration were not matched to this working branch; no deployment was performed in Phase 16.

---

## 7. IMPACT
*All impact metrics are strictly derived from verifiable system tests on the synthetic training dataset:*
- **100% Synthetic Training Dataset / Seeded Population Coverage**: Automated evaluation covered all 43 seeded expenses and 9 seeded procurement cases across 12 monthly periods; this is not evidence from a real institution.
- **Deterministic Ground-Truth Capture**: Successfully matched all **28 Ground-Truth Control Exceptions** spanning High (10), Medium (11), and Low (7) risk categories. The full analytical output contains **264 exception rows/records**, not 264 independent cases.
- **Local Configuration Verification**: `manage.py check` is clean and migrations are aligned locally; the synthetic loader is idempotent in development, opt-in only for isolated staging, and blocked in production.
- **Application Audit Traceability**: sensitive operations are captured in the Audit Trail with actor/context and before/after diffs where provided; DB-level append-only enforcement is not implemented or claimed.

---

## 8. LINK
- **GitHub Repository**: `Abdulhame709/Budget-Expenditure-Control-Audit-Analytics-Dashboard`
- **Working Branch**: `main`
- **Previously shared Manus Demo URL**: [open demo](https://auditdash-62j7lamg.manus.space/) — responded on 2026-10-02; this branch was not deployed, and the served revision is unverified.
