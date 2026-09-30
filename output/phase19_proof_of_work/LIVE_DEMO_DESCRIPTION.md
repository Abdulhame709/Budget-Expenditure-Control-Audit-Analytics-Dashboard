# Live Demo Description — System Overview & Access

### **Budget & Expenditure Control — Audit Analytics System**
*Interactive Web Application Preview Documentation*

---

## 1. Overview
The Live Demo is a fully operational, web-based implementation of the **Budget & Expenditure Control — Audit Analytics System**. It runs on a dedicated application stack combining:
- **Backend**: Django 5.2 LTS with Gunicorn WSGI workers.
- **Database**: PostgreSQL 16 providing complete transactional support and check constraints.
- **Frontend**: Responsive Arabic RTL interface powered by locally packaged Bootstrap 5.3.3 and Chart.js 4 (no external network dependencies).
- **Environment**: Secured with HTTPS proxying, automated static compression via WhiteNoise, and complete role-based permission gates.

---

## 2. Key Interactive Features

| Module | What You Can Inspect in the Live Demo |
|:---|:---|
| **Executive Dashboard** | Real-time budget variance metrics, expenditure trajectory charts, risk tier distribution (10 High, 11 Medium, 7 Low), and dynamic multi-parameter filtering. |
| **Audit Test Engine** | On-demand execution of 14 audit evaluators against the synthetic FY2026 dataset, returning 28 ground-truth exceptions with zero false positives. |
| **Exception Register** | Interactive table with filters by test code, risk level, and resolution status, with full modal detail views and audit action logging. |
| **Findings & Recommendations** | Structured auditor findings linking identified exceptions to underlying root causes and formal management action plans. |
| **Data Ingestion Pipeline** | Multi-step file upload with schema validation, error highlighting, and atomic database commits for CSV, Excel, and PDF formats. |
| **Reports & Exports** | 9 pre-built reports with print-optimized stylesheets (`@media print`) and dual-format exports (UTF-8 BOM CSV and native XLSX). |
| **Audit Trail (Governance)** | Comprehensive activity feed tracking user logins, failed attempts, data imports, engine runs, and entity modification diffs. |

---

## 3. Demo Credentials Summary

| Role | Username | Password | Purpose |
|:---|:---|:---|:---|
| **System Admin** | `admin` | `Admin-Training-2026!` | Full administrative inspection & user management |
| **Lead Auditor** | `ds_auditor` | `Dataset-Training-2026!` | Running audit tests, managing exceptions & findings |
| **Finance Officer** | `ds_finance` | `Dataset-Training-2026!` | Entering expenses, procurement orders & file uploads |
| **Executive / Mgmt** | `ds_mgmt` | `Dataset-Training-2026!` | Read-only dashboards and high-level risk reporting |

*All demonstration data is 100% synthetic (FY2026). No real-world entities, clients, or proprietary employer records are included.*
