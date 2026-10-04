# Budget & Expenditure Control — Audit Analytics System

| | |
|---|---|
| **Project** | Budget & Expenditure Control — Audit Analytics System |
| **Author / Owner** | Abdulhameed — Internal Audit & Financial Review Professional |
| **Role** | Internal Audit & Financial Review Professional |
| **Nature** | Professional Proof-of-Work / Training & Demonstration System |
| **Dataset / Data** | Synthetic Training Data |
| **Technology** | Django + PostgreSQL + Bootstrap RTL |

> ⚠️ **Synthetic Data** — كل البيانات في هذا النظام **اصطناعية بالكامل** (FY2026: أرقام وأقسام وموردون وهمية). لا تمثل أي جهة حقيقية، ولا علاقة لأي رقم أو اسم بجهة عمل المؤلف، ولا تُستخدم لأي قرار فعلي.
>
> **All data is 100% synthetic.** No real entity, client, employer, or real-world figure is represented anywhere in this repository.

> 🧍 **Ownership** — المالك: **Abdulhameed (Internal Audit & Financial Review Professional)**. لا توجد أي شركة حقيقية كـ Owner أو Client أو Employer في هذا المشروع.

---

## نظرة عامة / Overview

نظام داخلي (Internal Use) لمراقبة الموازنة مقابل التنفيذ (Budget vs Actual)، وتدقيق المصروفات والمشتريات، واكتشاف الاستثناءات وتصنيف المخاطر — بواجهة عربية RTL كاملة، ومحرك تدقيق من 14 اختبارًا آليًا، وتقارير قابلة للطباعة والتصدير.

**الحالة**: تأهيل إنتاجي مرحلي — مستودع GitHub العام متاح على `main` (آخر دمج متحقق: PR #4، commit `619725b` بتاريخ 2026-10-02) · صفحة Demo على Manus أعادت `HTTP GET 200` في 2026-10-02، لكن مطابقة النسخة المعروضة مع `main` وإعدادات المزوّد غير متحققة · **خط الأساس المحلي الموثق**: 353 اختبارًا آليًا ✅ · Django 5.2 · PostgreSQL حصريًا (لا SQLite). اجتياز الاختبارات أو وصول رابط العرض لا يثبت جاهزية مزوّد الاستضافة أو النطاق أو النسخ والاستعادة.

---

## 📌 Case Study (ملخص دراسة الحالة المهنية)

> **Problem:** Internal audit and financial control teams often rely on fragmented spreadsheets and manual sampling to monitor expenditures against approved budgets. This disconnected workflow delays exception detection, lacks automated risk scoring, and creates blind spots in procurement compliance and documentation audit trails.
>
> **Approach:** As an Internal Audit & Financial Review Professional, I designed an end-to-end, reproducible audit analytics system based on genuine internal control standards, clear segregation of duties, and systematic ground-truth exception rules.
>
> **Build:** I engineered a database-driven web application using Django 5.2 and PostgreSQL 16. The system incorporates role-based access control across 30 permissions, 14 automated audit test evaluators, a three-stage import pipeline (Excel/CSV/PDF), interactive KPI dashboards, 9 exportable reports, and full audit logging.
>
> **Result:** The automated engine independently evaluated a synthetic dataset of 43 expenses and 9 procurement cases, matching 28 Ground-Truth Control Exceptions with zero false positives against the predefined Ground-Truth test set across high, medium, and low risk tiers. The full analytical output contains 264 exception rows/records; these are not 264 independent cases.
>
> **Evidence:** The documented local PostgreSQL suite passes 353 automated tests and the published evidence hashes verify. The Manus demo returned HTTP GET 200 on 2026-10-02; the served revision has not been matched to the current GitHub `main`, and provider configuration/production readiness remain unverified. All training data remains synthetic.

*المستندات الكاملة لحزمة الـ Proof-of-Work متوفرة في المجلد [`output/phase19_proof_of_work/`](output/phase19_proof_of_work/):*
- [`PROJECT_PROOF.md`](output/phase19_proof_of_work/PROJECT_PROOF.md) — وثيقة إثبات المشروع (Problem · Owner · Solution · Role · Tools · Evidence · Impact · Link)
- [`PROJECT_CARD.md`](output/phase19_proof_of_work/PROJECT_CARD.md) — بطاقة المشروع التنفيذية
- [`CASE_STUDY.md`](output/phase19_proof_of_work/CASE_STUDY.md) — دراسة الحالة المركزة
- [`BEFORE_AFTER.md`](output/phase19_proof_of_work/BEFORE_AFTER.md) — مقارنة التحول قبل / بعد
- [`TECHNICAL_ARCHITECTURE.md`](output/phase19_proof_of_work/TECHNICAL_ARCHITECTURE.md) — ملخص المعمارية التقنية
- [`EVIDENCE_INDEX.md`](output/phase19_proof_of_work/EVIDENCE_INDEX.md) — فهرس الأدلة والبصمات
- [`DEMO_INSTRUCTIONS.md`](output/phase19_proof_of_work/DEMO_INSTRUCTIONS.md) — دليل تجربة النظام وحسابات العرض
- [`LIVE_DEMO_DESCRIPTION.md`](output/phase19_proof_of_work/LIVE_DEMO_DESCRIPTION.md) — وصف المعاينة الحية

---

## System Modules

| الوحدة | المسؤولية |
|---|---|
| `config` | الإعدادات (base/development/production) · URLs · WSGI · fail-fast |
| `accounts` | المصادقة + **30 permission code** ثابتة + middleware بوابة |
| `budget` | خطط الموازنة والفترات (من DB لا hardcode) |
| `expenses` | المصروفات · تحمّل ≤500K · تنبيهات المراجعة |
| `procurement` | المشتريات · 3 عروض إلزامية · Quote/Shipment/Receipt |
| `audit_register` | **قلب النظام**: 14 evaluator + تصنيف مخاطر + الاستثناءات + سجل التدقيق + المرفقات |
| `analytics` | لوحة المؤشرات (KPIs عربية/إنجليزية · فلاتر) |
| `reports` | 9 تقارير · HTML+Print CSS · CSV (BOM) · XLSX |
| `imports` | خط أنابيب الاستيراد Excel/CSV/PDF (معاينة → تحقق → تأكيد) |
| `governance` | الإعدادات الحوكمية · بوابات النظام |
| `reference` | القوائم المرجعية (عملات · فئات · موردون) |

```
واجهة RTL (Bootstrap 5.3 RTL · 45 قالبًا · شريط Synthetic أصفر)
        │
accounts/permission middleware (30 code) — بوابة على كل صفحة/فعل
        │
budget · expenses · procurement · imports · reference
        │
audit_register (14 evaluator → AuditException → سجل تدقيق + مرفقات)
        │
analytics (لوحة) · reports (9 تقارير + تصدير)
        │
PostgreSQL (حصري · D-01)  ← production: WhiteNoise · DEBUG=False · fail-fast
البيانات: system/datasets/training.py (Synthetic FY2026 + EXPECTED_PER_TEST)
```

---

## Repository Structure (ما هو فعليًا على GitHub)

```
.
├── README.md                                 # هذا الملف (GitHub README final)
├── LICENSE                                   # رخصة MIT
├── Procfile · render.yaml                    # ملفات إعداد النشر السحابي (Render / Gunicorn)
├── .gitignore                                # قواعد النشر/الاستبعاد (أدناه)
├── PROJECT_WORKSHOP7_COMPLIANCE_REVIEW.md    # سجل مراجعة امتثال (قراءة فقط)
├── system/                                   # النظام كاملًا (Django project)
│   ├── config/settings/{base,development,production} · urls · wsgi
│   ├── apps/ ×10 (accounts · budget · expenses · procurement ·
│   │            audit_register · analytics · reports · imports ·
│   │            governance · reference)
│   ├── datasets/training.py · templates/ · static/ · manage.py
│   ├── requirements.txt · .env.example       # المتطلبات + قالب البيئة
│   └── README.md                             # سجل المراحل التفصيلي
├── output/                                   # مخرجات وأدلة المراحل
│   ├── phase19_proof_of_work/                # حزمة إثبات الكفاءة (Proof-of-Work Docs)
│   ├── phase10_evidence/ phase11_evidence/ phase12_evidence/   # HTML/CSV/XLSX حيّة
│   ├── phase14_ux_review/UX_REVIEW.md        # تقرير مراجعة UX
│   ├── phase15_rc/RELEASE_CHECKLIST.md       # قائمة تحقق RC
│   └── audit_tests.csv · exception_register.csv
└── evidence/                                 # Proof/Evidence ( Synthetic )
    ├── evidence_01..04.png · validation_output.txt
    ├── checksums.txt                         # بصمات المنشور فقط (7× OK بعد clone)
    ├── screenshots/                          # جاهز لقطات الواجهة
    └── README.md
```

## الأرشيف المحلي — غير منشور (Local-only, never pushed)

| المسار | لماذا لا يُنشر |
|---|---|
| `.env` · `.venv/` · `.pgsql/` · `*.log` · `staticfiles/` · `__pycache__` | أسرار/بيئات/بيانات PostgreSQL محلية/حُزم — لا تدخل Git أبدًا |
| `data/` · `docs/` · `scripts/` · `requirements.txt` · `output/*.xlsx` | أرشيف مشروع قديم قد يحمل اسم شركة حقيقية داخل محتواه/بانراته — قرار مالك: لا نشر (قواعد في `.gitignore` بقسم مستقل) |
| `evidence/checksums.txt` (النسخة القديمة 17 بصمة) | استُبدلت بحزمة المنشور فقط؛ الأصل محفوظ في سجل git — لم يُحذف |

> ملاحظة: قد يختفي الأرشيف القديم من مساحة العمل عبر إعادة نسخ البيئة (كان untracked دائمًا) — لا يؤثر على اكتمال المستودع المنشور.

---

## How to run (Setup)

> كل الأوامر داخل `system/`.

### Windows local preview

من جذر المشروع، يمكن إدارة بيئة التطوير المحلية المعزولة بأداة واحدة:

```powershell
.\local-dev.ps1 setup    # أول تشغيل: venv + PostgreSQL + migrations + synthetic data
.\local-dev.ps1 start    # تشغيل PostgreSQL وDjango لاحقًا
.\local-dev.ps1 status   # عرض حالة الخادم والقاعدة
.\local-dev.ps1 stop     # إيقاف Django وPostgreSQL المحليين
```

- الواجهة: `http://127.0.0.1:8000/`
- PostgreSQL المحلي المعزول: `localhost:55432/audit_budget_system`
- حساب الإدارة التدريبي: `admin` / `Admin-Training-2026!`
- حساب المدقق الموصى به للاختبار: `ds_auditor` / `Dataset-Training-2026!`
- `.venv/` و`.pgsql/` و`.local-runtime/` محلية ومُستبعدة من Git.

```bash
python3.11 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt        # Django 5.2 · psycopg3 · whitenoise · pgserver · pandas …
cp .env.example .env                   # ثم عدّل DATABASE_URL
python -c "import secrets; print(secrets.token_urlsafe(50))"   # مفتاح تطوير عشوائي عند الحاجة
```

## How to configure PostgreSQL

**PostgreSQL إجباري (D-01) — SQLite غير مدعوم.**

```bash
# خيار أ — PostgreSQL حقيقي (موصى به للإنتاج):
#   أنشئ قاعدة + مستخدم ثم في .env:
#   DATABASE_URL=postgres://USER:PASS@127.0.0.1:5432/audit_budget_system

# خيار ب — بديل محلي مدمج (pgserver يشغّل PostgreSQL 16.2 بلا صلاحيات نظام):
#   DATABASE_URL=postgresql://postgres:@/audit_budget_system?host=$PWD/.pgsql
```

## Migration & Synthetic training data

```bash
python manage.py migrate                            # Development/staging migration
python manage.py load_training_dataset              # Development only by default
python manage.py createsuperuser                    # Named operator; never reuse demo credentials
```

- The loader is idempotent in development; staging requires an isolated database
  plus `DJANGO_ALLOW_SYNTHETIC_DATASET=true`; production always rejects it.
- Seeded `admin`/`ds_*` credentials are for local training only and cannot
  authenticate in production. Do not copy them to a hosted environment.
- Ground Truth and its expected results are retained unchanged: 43 expenses ·
  9 procurements · 18 quotations → the declared audit exceptions.

## How to run tests

```bash
python manage.py check                  # Django checks
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test                   # local PostgreSQL: 353/353
```

## Import workflow

The import center now supports Arabic/English column matching for fiscal years,
monthly periods, departments, expense categories, the chart of accounts,
suppliers, monthly budget lines, actual expenses, procurements and quotations.
Every target uses the same upload, preview, mapping, validation, confirmation
and audit-log workflow. Budget imports create or reuse a draft budget version;
approved versions remain locked.

The UI language defaults to Arabic. Authenticated users can switch Arabic /
English beside the username. Business data is not machine-translated: Arabic
names and descriptions remain exactly as entered.

Set SYSTEM_MODE=demo while synthetic records or demo accounts exist. Only set
SYSTEM_MODE=operational after a controlled cutover; operational mode hides
training banners and blocks loading the synthetic dataset.

1. من الواجهة: **إدارة النظام → رفع ملف** (Excel/CSV/PDF · ≤10MB، مع حد للصفوف/الأعمدة/صفحات PDF وتوسّع XLSX).
2. القالب النموذجي يُصدَّر من نفس الشاشة.
3. رفع → **معاينة** → تحقق (أخطاء/حجب) → تأكيد → تسجيل في سجل التدقيق.
4. PDF: قراءة/استخراج فقط عبر pipeline موحّد — **لا كتابة مباشرة في قاعدة البيانات**.

## Production qualification (not deployment approval)

**Deployment model:** one isolated application installation per customer; this
is not a shared multi-tenant service. Reuse the same release, but provision a
separate app instance, PostgreSQL database/roles, secrets, domain, private media
storage, and backup/restore boundary for each customer. Never copy one
customer's records or credentials into another installation.

Before any production use, provision and verify the chosen host, exact DNS name,
TLS-terminating proxy, and managed PostgreSQL database. Values below are
placeholders, not credentials; keep secrets in the provider secret manager, not
in Git or public logs.

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
export DJANGO_ENV=production
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
export DJANGO_ALLOWED_HOSTS=audit.example.org
export DATABASE_URL='postgresql://runtime_user:<secret>@db.example.org/audit_budget_system'
export MIGRATION_DATABASE_URL='postgresql://migration_user:<secret>@db.example.org/audit_budget_system'
export DJANGO_SECURE_SSL_REDIRECT=true
export DJANGO_SECURE_HSTS_SECONDS=0                 # raise only after domain/TLS review
python manage.py check --deploy
python manage.py collectstatic --noinput
DJANGO_USE_MIGRATION_DATABASE=true python manage.py migrate --noinput
python manage.py createsuperuser
```

- `DATABASE_URL` is the web/runtime connection; only a one-off release command
  may opt into the separately provisioned `MIGRATION_DATABASE_URL`.
- Do not run `load_training_dataset` in production. Demo accounts/data remain
  development-only; a staging seed needs an isolated DB and explicit opt-in.
- `check --deploy` currently reports W004 because `SECURE_HSTS_SECONDS=0` is
  intentional pending verification of the actual domain, HTTPS redirect and
  proxy. HSTS preload is disabled. A local check is not provider verification.
- The container collects static files at build and runs its web worker as a
  non-root user. Migrations are a separate release action; no dataset is seeded
  at startup. The Render blueprint disables automatic deploy and has not been
  provider-tested.
- `FileSystemStorage` for uploaded media may be ephemeral. Select and test
  private persistent storage, malware scanning, retention, backup and restore,
  and measured RPO/RTO before operational use.
- GitHub `main` contains the Phase 16 hardening changes through merged PR #4
  (`619725b`, 2026-10-02). No deployment of that exact revision, provider
  configuration, domain, media persistence, or restore procedure has been
  verified. See the historical phase checklist at
  [`output/phase15_rc/RELEASE_CHECKLIST.md`](output/phase15_rc/RELEASE_CHECKLIST.md)
  and the Phase 16 engineering record in `system/README.md`.

## Proof / Evidence

```bash
sha256sum -c evidence/checksums.txt     # بعد أي clone: OK×7 · صفر خطأ
```

- `evidence/` — رسوم PNG + `validation_output.txt` + حزمة بصمات قابلة للتحقق بعد النشر.
- `evidence/screenshots/` — المجلد المخصص لقطات الواجهة (يُعبَّأ من بيئة بها متصفح — KN-05).
- `output/phase1*_evidence/` — لقطات HTML الحيّة وأexports المراحل.
- سجل المراحل الكامل: `system/README.md` · قائمة RC: `output/phase15_rc/RELEASE_CHECKLIST.md`.

## Hosting Topology — فصل المزوّدين (بند إلزامي)

| الطبقة | المزوّد | المسؤولية |
|---|---|---|
| **Source repository** | **GitHub** | الكود المصدري + README + الأدلة فقط. **لا يوفّر** قاعدة بيانات ولا استضافة تطبيق. |
| **Database** | **PostgreSQL provider** (منفصل — مزوّد/خادم خاص بك) | قاعدة `audit_budget_system` + `pg_dump` احتياطي. مطلوب إنشاؤه خارج GitHub. |
| **Application hosting** | **Deployment provider** (منفصل) | تشغيل gunicorn خلف proxy (TLS + `/media/`) + `collectstatic` + متغيّرات الإنتاج. |

```
GitHub (source) ──deploy──▶ App host (gunicorn/nginx) ──DATABASE_URL──▶ PostgreSQL provider
     │                             │
     └─ لا استضافة ولا DB ─────────┘  (لا تفترض أيهما مضمّن في الآخر)
```

## License

**MIT License** — انظر [`LICENSE`](LICENSE) · اختيار صريح من المالك (2026-09-30):
استخدام/تعديل/توزيع حر مع ذكر المصدر والحفاظ على إشعار الحقوق، وبلا أي ضمان.

## Disclaimer

نظام تدريب/عرض (**Professional Proof-of-Work · Training & Demonstration System**) — لا يُستخدم كأداة تدقيق فعلية، ولا يمثل أي جهة حقيقية. البيانات: **Synthetic Training Data**. Live Preview/التطوير ≠ Production.
