# Before / After Transformation

### Project Evolution: From Static Spreadsheet Prototype to Production-Capable Training/Demo System

---

## 1. BEFORE (Static Analysis & Disconnected Workflows)
- **Tooling**: Manual, disconnected audit analysis prototype and spreadsheet-based workbook.
- **Data Flow**: Static Excel sheets with manual formula maintenance, vulnerable to broken cell references and formula overwrites.
- **Testing Approach**: Ad-hoc sampling of transactions; inability to systematically test 100% of expenditures.
- **Controls & Rules**: Unenforced control criteria; approval checks and budget overrun detection depended on manual visual inspection.
- **Audit Trails**: Zero immutable logging; modifications to amounts, dates, or classifications left no historical trace of who changed what and when.
- **Risk Assessment**: Subjective, unstandardized risk classification without structured remediation workflows.
- **Reporting**: Static charts embedded in workbooks requiring manual periodic updates and manual file distribution.

---

## 2. WHAT I BUILT (Working Database-Driven Web System)
- Engineered a modular, production-capable training/demo web system powered by **Django 5.2 LTS** and **PostgreSQL 16**.
- Designed a relational data architecture covering Chart of Accounts, Departments, Fiscal Periods, Multi-version Budgets, Expenses, Procurement, and Governance.
- Developed an automated **Audit Test Engine** containing 14 formal evaluators parameterized through database-driven thresholds.
- Implemented a secure, 3-stage **Import Validation Pipeline** supporting Excel, CSV, and PDF extraction with atomic commit protections.
- Integrated comprehensive **Role-Based Access Control (RBAC)** enforcing 30 explicit permission codes across 4 functional user roles.
- Crafted a localized **Arabic RTL interface** featuring responsive dashboards, dynamic Chart.js analytics, and print-ready reports.

---

## 3. AFTER (Published Demo / Release Candidate Training System)
A functioning Release Candidate demonstration system delivering:
1. **Relational Database**: Robust PostgreSQL storage with strict referential constraints and check constraints ($\text{Annual} = \sum \text{Months}$).
2. **Manual Entry**: Controlled, validated web forms for budgets, expenses, procurements, and reference master data.
3. **Excel/CSV Import**: Multi-stage pipeline with preview, column mapping, row-by-row validation, and batch atomic creation.
4. **PDF Review / Import**: Safe text extraction pipeline with data preview and manual confirmation before database insertion.
5. **Audit Test Engine**: 1-click execution across the seeded synthetic population with reproducible, deterministic results.
6. **Exception Register**: Centralized catalog of control exceptions with full metadata, financial exposure tracking, and status monitoring.
7. **Automated Risk Scoring**: Algorithmic classification into High, Medium, and Low risk tiers based on verifiable policy parameters.
8. **Findings & Recommendations**: Formal auditor issue tracker linking root causes, control implications, and agreed management action plans.
9. **Interactive Dashboard**: Real-time KPI cards, budget utilization rates, and multi-dimensional filterable charts.
10. **Custom Reports**: 9 specialized audit reports exportable to Print CSS, UTF-8 BOM CSV, and formatted XLSX workbooks.
11. **Complete History & Audit Trail**: Immutable transaction logging capturing logins, data imports, engine runs, status updates, and entity changes with before/after diffs.
