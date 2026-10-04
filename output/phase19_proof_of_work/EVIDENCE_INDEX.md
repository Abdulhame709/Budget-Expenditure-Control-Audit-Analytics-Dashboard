# Evidence Index — Verifiable Proof Artifacts

### Budget & Expenditure Control — Audit Analytics System
*Index of Verifiable Technical Evidence, Checksums, and Test Results*

---

## 1. Primary Evidence Channels

| Evidence Type | Artifact / Location | Verification Method | Status |
|:---|:---|:---|:---|
| **Source Code** | Public GitHub `main` | Repository and commit check | ✅ Repository reachable; Phase 16 hardening merged through PR #4 (`619725b`, 2026-10-02) |
| **Manus Demo URL** | https://auditdash-62j7lamg.manus.space/ | HTTP GET on 2026-10-02 | ⚠️ HTTP 200; served revision/provider configuration not matched to current GitHub `main` |
| **Automated Tests** | 353 tests across the Django test suite | `python manage.py test` on local PostgreSQL | ✅ 353/353 PASS; provider behavior unverified |
| **Ground Truth Tests** | `apps.audit_register.tests_dataset` (54 tests) | Exact equality match against 28 declared Ground-Truth Control Exceptions | ✅ Included in the 353/353 run |
| **Database Integrity** | 161 constraints in PostgreSQL catalog | SQL integrity check (0 orphaned rows) | ✅ Verified (PostgreSQL 16) |
| **Synthetic Dataset** | `system/datasets/training.py` | Loader tests; production guard | ✅ Idempotent in development; staging opt-in; always blocked in production |
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
- **Evidence 03**: `evidence/evidence_03_exceptions_by_risk.png` — Full analytical-output risk tier breakdown (61 High, 135 Medium, 68 Low; 264 records total).
- **Evidence 04**: `evidence/evidence_04_exceptions_by_test.png` — Exception frequencies across the 14 audit evaluators.
- **Phase 10/11/12 Live HTML Proofs**: Verified HTML and CSV exports in `output/phase10_evidence/`, `output/phase11_evidence/`, and `output/phase12_evidence/`.
