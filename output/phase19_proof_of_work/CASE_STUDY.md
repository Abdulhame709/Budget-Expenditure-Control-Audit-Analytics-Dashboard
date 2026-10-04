# Case Study: Audit Analytics & Expenditure Control System

**Problem:** Internal audit and financial control teams often rely on fragmented spreadsheets and manual sampling to monitor expenditures against approved budgets. This disconnected workflow delays exception detection, lacks automated risk scoring, and creates blind spots in procurement compliance and documentation audit trails.

**Approach:** As an Internal Audit & Financial Review Professional, I designed an end-to-end, reproducible audit analytics system based on genuine internal control standards, clear segregation of duties, and systematic ground-truth exception rules.

**Build:** I engineered a database-driven web application using Django 5.2 and PostgreSQL 16. The system incorporates role-based access control across 30 permissions, 14 automated audit test evaluators, a three-stage import pipeline (Excel/CSV/PDF), interactive KPI dashboards, 9 exportable reports, and full audit logging.

**Result:** The automated engine independently evaluated a synthetic dataset of 43 expenses and 9 procurement cases, matching 28 Ground-Truth Control Exceptions with zero false positives against the predefined Ground-Truth test set across high, medium, and low risk tiers. The full analytical output contains 264 exception rows/records, not 264 independent cases.

**Evidence:** The documented local PostgreSQL suite passes 353 automated tests and the published SHA-256 artifacts verify. The Manus demo returned HTTP GET 200 on 2026-10-02; its served revision has not been matched to the current GitHub `main`, and provider configuration remains unverified. No production-readiness approval is claimed. Training data is synthetic.
