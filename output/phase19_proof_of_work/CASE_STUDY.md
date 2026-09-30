# Case Study: Audit Analytics & Expenditure Control System

**Problem:** Internal audit and financial control teams often rely on fragmented spreadsheets and manual sampling to monitor expenditures against approved budgets. This disconnected workflow delays exception detection, lacks automated risk scoring, and creates blind spots in procurement compliance and documentation audit trails.

**Approach:** As an Internal Audit & Financial Review Professional, I designed an end-to-end, reproducible audit analytics system based on genuine internal control standards, clear segregation of duties, and systematic ground-truth exception rules.

**Build:** I engineered a database-driven web application using Django 5.2 and PostgreSQL 16. The system incorporates role-based access control across 30 permissions, 14 automated audit test evaluators, a three-stage import pipeline (Excel/CSV/PDF), interactive KPI dashboards, 9 exportable reports, and full audit logging.

**Result:** The automated engine independently evaluated a synthetic dataset of 43 expenses and 9 procurement cases, flagging exactly 28 predetermined exceptions with zero false positives across high, medium, and low risk tiers.

**Evidence:** The codebase contains 334 passing automated tests, verified SHA-256 evidence artifacts, a live interactive web deployment, and transparent synthetic training data.
