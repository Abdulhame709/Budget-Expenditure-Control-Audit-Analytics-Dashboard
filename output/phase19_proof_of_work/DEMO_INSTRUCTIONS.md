# Demo Instructions — Interactive Evaluation Guide

### Budget & Expenditure Control — Audit Analytics System
*Step-by-step guide to reviewing the system capabilities and testing user roles.*

---

## 1. Available Demonstration Accounts

| Username | Role | Password | Primary Permissions & Responsibilities |
|:---|:---|:---|:---|
| **`admin`** | Administrator | `Admin-Training-2026!` | Full administrative access, user/role management, and audit trail inspection. |
| **`ds_auditor`** | Auditor | `Dataset-Training-2026!` | Running the 14-test audit engine, reviewing exceptions, managing findings, and exporting reports. |
| **`ds_finance`** | Finance | `Dataset-Training-2026!` | Recording manual expenses, submitting procurement orders, uploading import files, and reviewing budgets. |
| **`ds_mgmt`** | Management | `Dataset-Training-2026!` | Executive visibility, reviewing high-level KPI trends, monitoring risk profiles, and read-only access. |

---

## 2. Guided Demonstration Workflows

### **Workflow A: The Audit Review & Exception Lifecycle (Recommended)**
1. **Login**: Navigate to `/accounts/login/` and log in with username **`ds_auditor`** and password `Dataset-Training-2026!`.
2. **Dashboard**: View `/dashboard/` to observe real-time financial KPIs (Budget, Actuals, Variance, Utilization) and risk distributions.
3. **Execute Engine**: Navigate to **إدارة النظام** $\rightarrow$ **الاختبارات الرقابية (المحرّك)** (`/audit/tests/`). Click the blue button **«تشغيل كل الاختبارات الرقابية»** (Run All Tests).
   - *Result*: The 14 evaluators process the 43 synthetic transactions, identifying exactly 28 control exceptions.
4. **Exception Register**: Open **إدارة النظام** $\rightarrow$ **سجل الاستثناءات** (`/audit/exceptions/`). Filter by Risk Level (**عالي** / High) or by test code (e.g., `T-BUD-01`).
5. **Manage Exception**: Click on an exception (e.g., `EXP-2026-0003`) to view detailed evidence, transaction context, and historical activity. Update the status from `Open` to `Acknowledged`.
6. **Findings & Recommendations**: Navigate to **إدارة النظام** $\rightarrow$ **النتائج والتوصيات** (`/audit/findings/`) to view or draft formal management recommendations.

---

### **Workflow B: Financial Operations & Import Validation**
1. **Login**: Log in as **`ds_finance`** (`Dataset-Training-2026!`).
2. **Manual Entry**: Navigate to **وحدات النظام** $\rightarrow$ **المصروفات الفعلية** $\rightarrow$ **تسجيل مصروف جديد** (`/expenses/new/`). Enter a transaction to observe immediate validation rules (amount cap $\le 500\text{K}$, active accounts, closed periods).
3. **Import Pipeline**: Open **وحدات النظام** $\rightarrow$ **الاستيراد** (`/imports/new/`). Download the standard CSV/Excel template, upload a sample file, and observe the 3-stage flow:
   - **Upload** $\rightarrow$ **Preview & Validation Errors** $\rightarrow$ **Atomic Confirmation**.

---

### **Workflow C: Comprehensive Reporting & Export**
1. **Reports Catalog**: Navigate to **التقارير** (`/reports/`). Select from 9 specialized reports.
2. **Budget vs. Actual**: Open report `budget-vs-actual`. Filter by department or fiscal period.
3. **Multi-Format Export**: Click **تصدير CSV** (encoded with UTF-8 BOM for immediate Excel compatibility) or **تصدير Excel (XLSX)** to download clean, numeric workbooks.
4. **Print-Ready CSS**: Use the browser's print command (`Ctrl+P` / `Cmd+P`) to preview the sanitized, branded print header with metadata.
