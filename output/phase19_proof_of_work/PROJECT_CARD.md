# Project Card — Audit Analytics & Budget Control System

### **Budget & Expenditure Control — Audit Analytics System**
*لوحة ونظام تحليل الموازنة والمصروفات والمشتريات والاستثناءات الرقابية*

---

### **Executive Summary**
| Dimension | Detail |
|:---|:---|
| **Author / Owner** | **Abdulhameed** |
| **Professional Role** | Internal Audit & Financial Review Professional / System Designer |
| **System Classification** | Professional Proof-of-Work · Training & Demonstration System |
| **Dataset** | 100% Synthetic Training Data (FY2026 Model Dataset) |
| **Technology Stack** | Django 5.2 LTS · PostgreSQL 16 · Gunicorn · WhiteNoise · Bootstrap 5.3 RTL · Chart.js |
| **Quality Baseline** | 334/334 Automated Tests Passing (100%) · Zero Issues on Django Check · Release Candidate |
| **License** | MIT License |

---

### **Core Capabilities**
1. **Budget Management**: Annual and monthly budget allocation by department and account, with database check constraints ensuring mathematical consistency ($\text{Annual} = \sum \text{Months}$).
2. **Actual Expenditure & Procurement Control**: Expense monitoring with single-transaction caps ($\le 500\text{K}$), mandatory 3-quotation procurement rules, and closed-period posting enforcement.
3. **Automated Audit Engine**: 14 extensible control evaluators checking for budget overruns, unexpected variances, split orders, unapproved expenses, and duplicate invoices.
4. **Exception Register & Risk Engine**: Automated classification into High, Medium, and Low risk tiers, with a full management remediation workflow (Open $\rightarrow$ Acknowledged $\rightarrow$ Resolved).
5. **Interactive Dashboard & Reporting**: Arabic-first RTL interface with real-time KPI aggregations, responsive Chart.js visual trends, and 9 customizable reports exportable to Print-ready HTML, UTF-8 BOM CSV, and XLSX.
6. **Governance & Audit Trail**: Granular 30-permission RBAC across 4 roles, full before/after diff tracking for sensitive entities, and universal attachment handling.
