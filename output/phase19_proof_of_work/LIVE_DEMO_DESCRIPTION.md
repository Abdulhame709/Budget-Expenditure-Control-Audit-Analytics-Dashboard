# Live Demo Description — System Overview & Access

### **Budget & Expenditure Control — Audit Analytics System**
*Previously shared Manus Demo — page response checked 2026-10-02; served revision unverified*

> A read-only fetch of the external URL returned the demo page. This confirms
> reachability at check time only: it does not identify the deployed commit or
> verify hosting/database configuration. Phase 16 changes were not deployed.
> The returned page included operational environment diagnostics and a
> production-readiness claim; review/gate that public content before relying on
> it. Bootstrap/Chart.js still use an external CDN, so offline delivery is not
> established.

---

## 1. Overview
The system is a web-based training implementation of the **Budget & Expenditure Control — Audit Analytics System**. The local codebase is built from:
- **Backend**: Django 5.2 with Gunicorn WSGI configuration.
- **Database**: PostgreSQL 16 in the local verification setup; managed-provider behavior remains unverified.
- **Frontend**: Responsive Arabic RTL templates; Bootstrap RTL and Chart.js are referenced via an external CDN (offline availability is not established).
- **Static/media**: WhiteNoise is configured for static files; persistent private media storage and provider-side TLS/proxy behavior still require validation.

---

## 2. Key Interactive Features

| Module | What You Can Inspect in the Live Demo |
|:---|:---|
| **Executive Dashboard** | Real-time budget variance metrics, expenditure trajectory charts, risk tier distribution (10 High, 11 Medium, 7 Low), and dynamic multi-parameter filtering. |
| **Audit Test Engine** | On-demand execution of 14 audit evaluators against the synthetic FY2026 dataset, matching 28 Ground-Truth Control Exceptions with zero false positives against the predefined Ground-Truth test set. |
| **Exception Register** | Interactive table with filters by test code, risk level, and resolution status, with full modal detail views and audit action logging. |
| **Findings & Recommendations** | Structured auditor findings linking identified exceptions to underlying root causes and formal management action plans. |
| **Data Ingestion Pipeline** | Multi-step file upload with schema validation, error highlighting, and atomic database commits for CSV, Excel, and PDF formats. |
| **Reports & Exports** | 9 pre-built reports with print-optimized stylesheets (`@media print`) and dual-format exports (UTF-8 BOM CSV and native XLSX). |
| **Audit Trail (Governance)** | Comprehensive activity feed tracking user logins, failed attempts, data imports, engine runs, and entity modification diffs. |

---

## 3. Demo Credentials Summary

| Role | Username | Password | Purpose |
|:---|:---|:---|:---|
| **System Admin (training only)** | `admin` | `Admin-Training-2026!` | Training-only administrative inspection; not a production credential |
| **Lead Auditor** | `ds_auditor` | `Dataset-Training-2026!` | Running audit tests, managing exceptions & findings |
| **Finance Officer** | `ds_finance` | `Dataset-Training-2026!` | Entering expenses, procurement orders & file uploads |
| **Executive / Mgmt** | `ds_mgmt` | `Dataset-Training-2026!` | Read-only dashboards and high-level risk reporting |

*All accounts listed here are Demo/Training accounts only and must never be treated as production credentials. The recommended public walkthrough uses the lower-privilege `ds_auditor` account. All demonstration data is 100% synthetic (FY2026); no real-world entities, clients, or proprietary employer records are included.*
