# Evidence Index — Verifiable Proof Artifacts

### Budget & Expenditure Control — Audit Analytics System
*Index of Verifiable Technical Evidence, Checksums, and Test Results*

---

## 1. Primary Evidence Channels

| Evidence Type | Artifact / Location | Verification Method | Status |
|:---|:---|:---|:---|
| **Source Code** | GitHub Repository (`main` / working branch) | `git status` · `git log` | ✅ Verified clean HEAD |
| **Published Demo / Live Demonstration** | https://auditdash-62j7lamg.manus.space/ | Public URL check when available | ⚠️ Hosting availability must be rechecked at presentation time |
| **Automated Tests** | 334 tests across 11 test modules | `python manage.py test` | ✅ 334/334 PASS (100%) |
| **Ground Truth Tests** | `apps.audit_register.tests_dataset` (53 tests) | Exact equality match against 28 Ground-Truth Control Exceptions | ✅ 53/53 PASS (0 errors) |
| **Database Integrity** | 161 constraints in PostgreSQL catalog | SQL integrity check (0 orphaned rows) | ✅ Verified (PostgreSQL 16) |
| **Synthetic Dataset** | `system/datasets/training.py` | `manage.py load_training_dataset` | ✅ 100% Idempotent |
| **Published Proofs** | `evidence/checksums.txt` (7 files) | `sha256sum -c evidence/checksums.txt` | ✅ 7/7 OK |

---

## 2. Checksum Manifest (`evidence/checksums.txt`)
All 7 published evidence deliverables have cryptographically verified SHA-256 hashes:
```text
output/audit_tests.csv: OK
output/exception_register.csv: OK
evidence/evidence_01_budget_vs_actual_by_dept.png: OK
evidence/evidence_02_monthly_trend.png: OK
evidence/evidence_03_exceptions_by_risk.png: OK
evidence/evidence_04_exceptions_by_test.png: OK
evidence/validation_output.txt: OK
```

---

## 3. Visual & Analytical Artifacts
- **Evidence 01**: `evidence/evidence_01_budget_vs_actual_by_dept.png` — Budget vs. Actual expenditure distribution by department.
- **Evidence 02**: `evidence/evidence_02_monthly_trend.png` — Monthly expenditure trajectory across FY2026.
- **Evidence 03**: `evidence/evidence_03_exceptions_by_risk.png` — Risk tier breakdown (10 High, 11 Medium, 7 Low).
- **Evidence 04**: `evidence/evidence_04_exceptions_by_test.png` — Exception frequencies across the 14 audit evaluators.
- **Phase 10/11/12 Live HTML Proofs**: Verified HTML and CSV exports in `output/phase10_evidence/`, `output/phase11_evidence/`, and `output/phase12_evidence/`.
