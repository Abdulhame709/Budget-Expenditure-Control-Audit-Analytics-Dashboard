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

**الحالة**: Release Candidate (RC) · Published Demo / Live Demonstration · **المجموعة**: 334 اختبارًا آليًا ✅ (281 وحدة/تكامل + 53 ground-truth) · Django 5.2 LTS · PostgreSQL 16 حصريًا (لا SQLite).

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
> **Evidence:** The codebase contains 334 passing automated tests, verified SHA-256 evidence artifacts, a documented Published Demo / Live Demonstration, and transparent synthetic training data.

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

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # Django 5.2 · psycopg3 · whitenoise · pgserver · pandas …
cp .env.example .env                   # ثم عدّل DATABASE_URL
python -c "import secrets; print(secrets.token_urlsafe(50))"   # مولّد SECRET_KEY
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

## Migration & How to load training data

```bash
python manage.py migrate                            # 0 معلَّق · لا انحراف
python manage.py load_training_dataset              # idempotent — آمن للتكرار
python manage.py createsuperuser
# بعد التحميل: admin / auditor / finance / management — Demo-Training-2026!
#               ds_* — Dataset-Training-2026!
# المحتوى: 43 مصروف · 9 مشتريات · 18 عرضًا → 28 استثناء متوقع + 42 مرفقًا
```

## How to run tests

```bash
python manage.py check                  # نظيف
python manage.py test                   # 334/334 (~2 دقيقة)
python manage.py test apps.audit_register.tests_dataset   # ground-truth فقط (53)
```

## Import workflow

1. من الواجهة: **إدارة النظام → رفع ملف** (Excel/CSV · ≤10MB · UTF-8 · أعمدة موثقة).
2. القالب النموذجي يُصدَّر من نفس الشاشة.
3. رفع → **معاينة** → تحقق (أخطاء/حجب) → تأكيد → تسجيل في سجل التدقيق.
4. PDF: قراءة/استخراج فقط عبر pipeline موحّد — **لا كتابة مباشرة في قاعدة البيانات**.

## Deployment prerequisites

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production   # fail-fast عند أي نقص
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
export DJANGO_ALLOWED_HOSTS=audit.example.org
export DJANGO_SECURE_SSL_REDIRECT=true
export DJANGO_SECURE_HSTS_SECONDS=31536000
export DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=true
export DJANGO_SECURE_HSTS_PRELOAD=true
# + DATABASE_URL (PostgreSQL إنتاجي) · DJANGO_CSRF_TRUSTED_ORIGINS عند تباين النطاق
python manage.py check --deploy          # = 0 issues مع الأعلام أعلاه
python manage.py collectstatic --noinput
gunicorn config.wsgi:application         # خلف proxy يوفّر TLS و /media/
```

- WhiteNoise يقدّم `/static/` · `/media/` عبر مسار proxy · فشل مبكر: SECRET_KEY ضعيف · ALLOWED_HOSTS فارغ · DATABASE_URL ناقص.
- بوابة النشر الكاملة (22 بندًا): `output/phase15_rc/RELEASE_CHECKLIST.md`.
- النسخ الاحتياطي: `pg_dump -Fc` + `media/` + ضمان `.env` بقناة منفصلة.

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
