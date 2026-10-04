# Audit Analytics & Budget Control System

> نظام التحليل الرقابي والموازنة والمصروفات والمشتريات — **Independent Training & Demonstration System** (D-04).
> بيانات النظام تدريبية: Synthetic Training Data.

**Stack (D-01):** Django 5.2 + **PostgreSQL** (لا SQLite) · عربي RTL أولًا (D-08).

## البنية (PHASE 2)
```
system/
├── manage.py               # نقطة التشغيل
├── requirements.txt        # Django · psycopg · dj-database-url · dotenv · whitenoise · gunicorn
├── .env / .env.example     # DATABASE_URL و إعدادات البيئة (لا يُرفع .env)
├── config/                 # المشروع: settings (base/development/staging/production) · urls · views · tests
├── apps/                   # 10 تطبيقات حسب Architecture المعتمدة:
│   accounts  reference  budget  expenses  procurement
│   imports   analytics  audit_register  reports  governance
├── templates/              # base.html (RTL + Bootstrap 5 RTL) · home · 403/404/500
├── static/css/app.css
├── scripts/setup_postgres.sh  # تجهيز خوادم PostgreSQL المحلية
├── logs/  media/  staticfiles/   (gitignored)
└── .pgsql/                 # بيانات PostgreSQL المحلية (gitignored)
```

## التشغيل
```bash
cd system
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bash scripts/setup_postgres.sh        # PostgreSQL محلي (انظر الملاحظة أدناه)
.venv/bin/python manage.py makemigrations accounts
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test       # اختبارات الإثبات (PHASE 2)
.venv/bin/python manage.py runserver 0.0.0.0:8000
```
التشغيل الإنتاجي يتطلب `config.settings.production`/`staging`، أسرارًا ومضيفين دقيقين، PostgreSQL TLS، ومراجعة مزوّد الاستضافة؛ لا توجد موافقة نشر في هذا السجل.

## ملاحظة بيئية (مُصرَّح بها — Blocker مُعالج)
مستودعات apt وGitHub-CDN محجوبة في بيئة العمل هذه، لذا تُجهَّز PostgreSQL المحلية عبر
binariess **الحقيقية** المضمّنة في حزمة `pgserver` (PyPI) — خادم PostgreSQL فعلي 16.x
على `127.0.0.1:5432` — وليس بديلًا تقنيًا. `DATABASE_URL` في `.env` هو المدخل الوحيد للاتصال.

## قواعد ثابتة
- D-01: PostgreSQL حصريًا · D-04: مستقل، المالك Abdulhameed · D-03: Synthetic فقط.
- كل مرحلة تُعتمد قبل التالية؛ Commit منطقي بعد كل مرحلة معتمدة (D-09).

## المصادقة والصلاحيات (PHASE 3 — RBAC)
- **4 أدوار**: `admin` (كل الصلاحيات) · `auditor` (18) · `finance` (12) · `management` (5 عرض فقط).
- **30 صلاحية** (29 في PHASE 3 + `periods.post_closed` أضيفت في PHASE 4) مخزّنة في
  قاعدة البيانات (`permissions` + `roles` + `role_permissions`) — الكتالوج مُرحّل عبر
  `accounts/0003_seed_rbac` + `0004_seed_periods_permission`.
- **حماية على 3 مستويات**: صفحة (الرابط المباشر لغير المصرّح → **403**)،
  إجراء (POST لغير المصرّح → **403**)، كائن (لا تعديل لسجلك/أدوارك — object rule).
- **سجل تدقيق** (`audit_logs`): دخول/فشل دخول/خروج/إنشاء وتعديل مستخدم/تغيير الأدوار —
  مع JSON diff (بدون كلمات مرور) + IP/User-Agent · صفحة `/audit-trail/`.
- صفحات: `/accounts/login/` · `/accounts/users/` · `/accounts/roles/` · `/accounts/profile/`.
- **اختبارات**: `manage.py test` → **27/27** (7 دخان PHASE 2 + 20 اختبار صلاحيات حقيقي
  بردود HTTP 302/403 — لا إخفاء أزرار).
- مستخدمو عرض تجريبي (بيئة التطوير فقط، `is_demo=True`):
  `admin` بكلمة مرور `Admin-Training-2026!`، وحسابات `ds_admin` · `ds_auditor` · `ds_finance` · `ds_mgmt` بكلمة مرور `Dataset-Training-2026!` (تطوير محلي فقط؛ الحسابات الموسومة Demo مرفوضة من مصادقة الإنتاج، ولا تُنسخ بيانات اعتمادها إلى الإنتاج).

## وحدات البيانات الأساسية (PHASE 4)
- **6 وحدات CRUD** على `/reference/`: سنوات مالية · فترات شهرية · إدارات ·
  دليل حسابات · تصنيفات مصروفات · موردون — بحث + فلترة + ترقيم صفحات +
  Active/Inactive · عربي RTL · آلة CRUD واحدة قابلة للتوسّع (registry في
  `apps/reference/views.py`).
- **القيود**: تداخل السنوات المالية مرفوض · فريد (سنة، شهر) · الفترة داخل نطاق
  السنة وأول/آخر الشهر · منع الدورات في شجرة الإدارات والحسابات ·
  `expense_category` فقط لحسابات نوع «مصروفات» · FK **PROTECT** (RESTRICT) +
  قيود CHECK في قاعدة البيانات.
- **قاعدة الفترة المغلقة**: `reference.services.require_period_postable()` —
  نقطة إنفاذ واحدة ترفض أي تسجيل في فترة مغلقة/غير نشطة إلا بصلاحية
  `periods.post_closed` (admin افتراضيًا)، وكل تجاوز مُصرَّح يُكتب في Audit Trail
  (action=`closed_period_override`). فتح/إغلاق الفترة فقط عبر زر مُدقّق
  (`period_status_changed`).
- **السجل**: كل إنشاء/تعديل/حذف مرجعي يُسجَّل (`entity_created/updated/deleted`)
  بـ diff قبل/بعد + المنفّذ؛ الحذف المرتبط مرفوض برسالة عربية (يُعطَّل بدلًا منه).
- **اختبارات**: 69/69 (27 السابقة + 42 اختبار علاقات/قيود/CRUD HTTP/بحث/ترقيم/قاعدة الفترة).

## إدارة الموازنة (PHASE 5)
- **البنية**: `Budget` (واحدة لكل سنة مالية) → `BudgetVersion` (مسودة ⇄ معتمدة؛
  المراجعة = نسخة جديدة بنسخ السطور) → `BudgetLine` (إدارة × حساب × تصنيف + 12 شهرًا).
- **السنوية** = مجموع الأشهر الـ 12 — محسوبة في `clean()` **وقيد CHECK** في
  PostgreSQL (`chk_line_annual_is_monthly_sum`) · مبالغ `NUMERIC(14,2)` بلا سالب ·
  فريد (نسخة، إدارة، حساب) · حسابات نوع «مصروفات» فقط · التصنيف يُرَث من الحساب.
- **الدورة**: إدخال يدوي ← اعتماد (يُقفل النسخة + يُسجَّل `budget_approved`) ←
  أي تعديل يتطلب **نسخة مراجعة** تنسخ السطور (`budget_version_created`) —
  نسخة معاينة التحليل = **آخر نسخة معتمدة** (`get_analysis_version`).
- **الأرقام كلها من DB**: ملخص `/budget/versions/<id>/summary/` بـ
  SUM/aggregate (سنوي، شهري، حسب الإدارة/الحساب/التصنيف) — لا أرقام ثابتة.
- **أساس لاحق (جاهز ومُختبَر)**: `monthly_budget_map` (Variance)،
  `is_budgeted` / `line_for` (Out-of-Budget)، ملخص الميزانية (Budget vs Actual)
  — التنفيذ الكامل وارد مع Actuals في مرحلة لاحقة، لا Audit Engine الآن.
- **الصلاحيات**: عرض `budget.view` (مدقق/مالية) · إدخال واعتماد `budget.edit`
  (مالية/مدير) · الإدارة (management) بلا `budget.view` وفق مصفوفة PHASE 3.
- **اختبارات**: 96/96 (27 اختبار PHASE 5: حسابات، قيود، دورة، صلاحيات HTTP، أساس التحليل).

## المصروفات الفعلية (PHASE 6)
- **إدخال يدوي كامل** على `/expenses/`: رقم مصروف تلقائي `EXP-سنة-تسلسل` (أو يدوي
  فريد) · تاريخ · **فترة محاسبية** · إدارة · حساب (COA) · تصنيف (يُرَث) · مورّد
  اختياري · بيان · مبلغ `NUMERIC(14,2)` موجب · عملة (USD/SAR/YER) · دفع/مرجع
  دفع · مرجع فاتورة · مستند مرفق (≤10MB) · مرجع اعتماد (يُختَم باسم المعتمِد).
- **الروابط**: `period` FK (قاعدة الفترة المغلقة سارية: finance → **403**،
  admin → تمرير + `closed_period_override` في السجل) · `account` من نوع مصروفات
  فقط (COA) · الربط بالميزانية **حيّ من DB** في صفحة التفاصيل (سطر النسخة
  المعتمدة لـ إدارة+حساب + مبلغ الشهر) عبر `expense_budget_context`.
- **ضد التكرار**: رقم فريد · فريد جزئي (مورّد + مرجع فاتورة) · رفض التكرار
  التام (تاريخ+مورّد+مبلغ+مرجع) برسالة عربية · تواريخ داخل الفترة ·
  إدارات/حسابات/موردين نشطين فقط.
- **الشاشات**: قائمة (بحث + فلترة الفترة/الإدارة/الحساب/التصنيف/المورّد/العملة/
  الاعتماد/المدى الزمني + إجمالي SUM من DB + ترقيم) · تفاصيل · إنشاء/تعديل ·
  **عرض المرفق** (مصادَقة + مُسجَّل `expense_attachment_viewed` — لا وصول مباشر
  للـ media) · **تصدير CSV** (UTF-8 BOM) بنفس الفلاتر + سجل `expenses_exported`.
- **سجل التدقيق**: `entity_created/entity_updated` بـ diff كامل + المرفق/الاعتماد.
- **اختبارات**: 133/133 (37 اختبار PHASE 6).

## إدارة المشتريات (PHASE 7)
- **الجداول**: `procurements` + `procurement_quotations` — ترقيم تلقائي
  `PR-YYYY-NNNNN` (يُولَّد من نفس أرقام المالية أو يُدخل يدويًا) · مبلغ
  CHECK>0 · إدارات/موردين/حسابات نشطين فقط · حسابات نوع `expense` فقط ·
  `expense_category` يُشتق من الحساب تلقائيًا.
- **حالة السجل**: `draft/pending/approved/ordered/received/cancelled` (6 حالات) ·
  **الحذف مسموح لـ draft/cancelled فقط** (الباقي PROTECT عمليًا — رسالة عربية).
- **PO / الاعتماد**: `purchase_order` اختياري (فارغ = «بدون PO») ·
  `approval_reference` + `approved_by/at` تُختم تلقائيًا عند وضع المرجع وتُلغى
  عند مسحه (قرارات C7) · **الاعتماد لا يُحوَّل الحالة تلقائيًا**.
- **عروض الموردين**: جدول مستقل لكل سجل — **عرض واحد لكل مورّد**
  (`uq_quote_per_supplier`) · مبلغ CHECK>0 · مورّد مفعّل فقط · CASCADE مع السجل ·
  الأعمدة: مورّد/مبلغ/تاريخ العرض/مرجع/ملاحظات.
- **الدفع**: `payment_method` (نقدي/تحويل/شيك/آجل) + `payment_reference` اختياري.
- **المرفقات**: ≤10MB (`MAX_ATTACHMENT_MB`) — عبر مسار `/attachment/`
  (مصادَقة + سجل `procurement_attachment_viewed` — لا وصول مباشر للـ media).
- **حقائق الاختبارات الرقابية** (قاعدة للاختبارات القادمة):
  `services.procurement_audit_context(record)` تُرجع
  `has_po · has_approval · quote_count · lowest_quote · quotes[] · has_attachment ·
  supplier{code,name,tax_number,email,is_active} · amount · date · department ·
  account · account_type · category · status · is_cancelled · payment_* ·
  approval_reference · approved_by/at · attachment · reference_number` — تُعرض
  في صفحة التفاصيل في لوحة «حقائق اختبارات الرقابة».
- **الفلاتر**: بحث حر (رقم/وصف/PO) + الحالة + `has_po` + `has_approval` +
  الإدارة/المورّد/الحساب + مدى تاريخ + إجمالي SUM من DB + ترقيم.
- **سجل التدقيق**: `entity_created/updated/deleted` لـ **procurement و quotation**
  بنفس بنية diff المراحل السابقة.
- **اختبارات**: 156/156 (23 اختبار PHASE 7 — تحقق العلاقات PROTECT/CASCADE
  والوحيدة وحقائق السياق وHTTP والصلاحيات والفلاتر والمرفق).

## خط الاستيراد (PHASE 8)

يدعم مركز الاستيراد حاليًا السنوات والفترات المالية، الإدارات، تصنيفات
المصروفات، الدليل المحاسبي، الموردين، سطور الموازنة الشهرية، المصروفات
الفعلية، المشتريات وعروض الأسعار. تمر جميعها بمراحل المعاينة والمطابقة
والتحقق والتأكيد الذري وسجل التدقيق، ولا تُعدّل نسخة موازنة معتمدة.

متغير SYSTEM_MODE له قيمتان: demo للبيانات الاصطناعية الحالية، وoperational
بعد تنفيذ قطع تشغيلي نظيف وإزالة الحسابات والبيانات التدريبية. لا يُستخدم
الوضع التشغيلي لإخفاء حقيقة أن قاعدة البيانات ما زالت تحتوي بيانات تدريبية.
- **التدفق**: Upload → Extract → Preview → Field Mapping → Validation →
  Error Review → User Confirmation → Import → Import Log — كل خطوة مُسجَّلة
  في `job_log` + AuditLog (`entity_created/updated` للـ Job · `data_imported`
  عند التنفيذ · `import_file_downloaded` عند تنزيل الأصل).
- **الصيغ**: CSV (pandas · utf-8-sig/cp1256/latin-1 · فواصل , ; tab |) ·
  Excel xlsx (pandas + openpyxl) · **PDF (pdfplumber)**: جداول أولًا ثم نص
  مقسّم — لا يدخل PDF قاعدة البيانات مباشرة أبدًا؛ يمر نفس مسار
  Preview/Mapping/Validation/Confirmation. **OCR طبقة اختيارية** تظهر
  كتحذير صريح عند غياب المحتوى المنظم — النظام الأساسي لا يشترطها.
- **المطابقة**: اقتراح تلقائي (أعمدة ar/en) + نموذج مطابقة يدوي — الحقول
  الإلزامية: التاريخ/الإدارة/الحساب/البيان/المبلغ.
- **التحقق لكل صف**: تاريخ (بما فيها Excel serial) · فترة شهرية موجودة
  (مغلقة = خطأ لمن لا يملك `periods.post_closed` — وتحذير لمن يملكه) ·
  مورّد/إدارة/حساب بالإرجاع للبيانات المرجعية · قواعد `Expense.clean`
  (حساب مصروف نشط · مبلغ >0 · تكرار قاعدة البيانات) ·
  **كشف التكرار**: داخل الملف + مقابل قاعدة البيانات (مورّد+فاتورة).
- **الملخص المطلوب**: total · valid · invalid · duplicate · errors ·
  warnings (بالعدّ + جدول أخطاء بالصف والرسالة) — معادلة عرض:
  `total = valid + invalid + duplicate`.
- **التنفيذ**: تأكيد المستخدم أولًا · `transaction.atomic` لـ**الصفوف الصالحة
  فقط** · أرقام EXP تسلسلية · ختم اعتماد عند وجود `approval_reference` ·
  الصفوف غير الصالحة لا تُدخل أبدًا.
- **حفظ الأصل**: `source_file` لا يُحذف أبدًا (دليل) — الإلغاء يُبقي الملف ·
  تنزيل مُصرَّح ومُسجَّل · حد 10MB (`MAX_FILE_MB`).
- **الصلاحيات**: الكتالوج **30 كودًا بلا تغيير** — `imports.view`
  (عرض/تنزيل) · `imports.run` (رفع/تحقق/تنفيذ/إلغاء) — finance+admin فقط.
- **عينات Synthetic**: `samples/expenses_sample.{csv,xlsx,pdf}` (الـCSV
  يتعمّد صفًا سالبًا + صفًا مكررًا لعرض Error Review).
- **اختبارات**: 187/187 (31 اختبار PHASE 8 — استخراج الثلاث صيغ · PDF
  يدوي · OCR اختياري · مطابقة · مصفوفة تحقق · فترة مغلقة · تكرار · تنفيذ ·
  RBAC · حفظ الأصل · كتالوج 30).

## محرّك الاختبارات الرقابية (PHASE 9)
- **الجداول**: `audit_tests` (القواعد) + `audit_runs` + `audit_test_results` +
  `audit_exceptions` — المحرك يقرأ القواعد من DB وليس hard-coded.
- **البذرة**: الاختبارات الـ14 المعتمدة من المشروع السابق (T-BUD-01..03 ·
  T-PROC-01..05 · T-EXP-01..06) — منطقها مرجع مُعاد بناؤه على مخطط النظام
  الجديد، وكل عتبة P1–P9 معلَّمة **Synthetic/Training Rule** في نص القاعدة
  والمعاملات (`synthetic_rule=true`) — لا عتبة تُقدَّم كسياسة حقيقية.
- **حقول كل اختبار**: Test ID · Name · Objective · Rule · Parameters (JSONB) ·
  Data Source · Expected Result · Exception Type · Default Risk ·
  Auditor Action · Active/Inactive — **قابلة للإنشاء/التعديل/التعطيل من
  الواجهة** (`audit.rules.manage`) — إلغاء علامة Synthetic مرفوض بحكم هذه
  المرحلة.
- **المنفّذ (`engine_key`)**: 14 محرّكًا مسجّلًا في `services.EVALUATORS` —
  اختبار جديد = منفّذ موجود بمعاملات مستقلة (مثلًا min_quotes=4).
- **التشغيل**: اختبار واحد · المحدد من الجدول · **كل المفعّلة** (`audit.run`) —
  `resolve_tests` يحترم Active/Inactive (المحدد قد يشغّل معطّلًا عمدًا).
- **التخزين**: كل تشغيل برقم `AR-YYYY-NNNNN` + نتائج pass/flagged/_fail مع
  **تفسير** و**لقطة المعاملات وقت التشغيل** + استثناءات كل منها:
  `source_type/source_id/source_ref` (تتبّع فوري إلى معاملة المصروف/المشتريات
  + تركيبة الموازنة) · `explanation` يذكر القيم الفعلية مقابل العتبة ·
  شدّة S1/S2/S3 + خطر **معادلة 3×3** (RR-01..RR-06 بعتبات من `risk_bands`
  في معاملات الاختبار).
- **الأنواع**: `pass` بلا استثناءات · `flagged` مع استثناءات · `fail` عند
  خطأ المنفّذ (لا يُقدَّم كنجاح).
- **الاستثناءات**: سجل مركزي بفلاتر (حالة/خطر/اختبار/تشغيل/بحث) وحالات
  مفتوح→قيد الدراسة→مُعالج (`exceptions.manage`) مُسجَّلة في دليل التدقيق.
- **الصلاحيات**: كتالوج 30 كودًا — `audit.view`/`audit.run`/
  `audit.rules.manage`/`exceptions.view`/`exceptions.manage` (auditor كامل ·
  finance بلا وصول · management عرض استثناءات فقط حسب مصفوفة الأدوار المعتمدة).
- **البيانات غير المتاحة**: حقل استلام المشتريات وحقل PO على المصروف
  وحالة Partial للمستند غير موجودة في المخطط — تُعطَّل بمعامل صريح
  مُعلَن (`check_receiving=false` · `check_partial=false`) مع نص قاعدة يصرّح
  بها (لا يُفترض بيانات غير موجودة).
- **اختبارات**: 225/225 (38 اختبار PHASE 9 — اكتمال البيانات المُدرجة ·
  المنفّذات الـ14 (مُعلِّم + نظيف) · مصفوفة الخطر · تخزين التشغيل
  والتتبّع · تغيير العتبة من DB يغيّر النتيجة · RBAC · الكتالوج 30).

---

## PHASE 10 — دورة المعالجة الرقابية (Audit Remediation Cycle)

**Cycle:** Audit Test → Exception → Risk Assessment → Finding → Recommendation → Status.
EntryPoint: `/audit/` (dcc) — **"Dashboard" في سلسلة التنقل = هذه اللوحة المصغّرة (navigation
start point)؛ وحدة DB Dashboard الكاملة تبقى محظورة ولم تُطلب.**

### Exception (توسعة PHASE 10)
- حقول موجودة من PHASE 9 + **auditor_action** (نسخة snapshot من `test.auditor_action`
  وقت إنشاء الاستثناء — القيمة الحالية دائماً في runtime) + **evidence** (FileField).
- **رفع الدليل**: `/audit/exceptions/<pk>/evidence/` — ملفات PDF/صور حتى 10MB، استبدال (لا تكديس)،
  يسجّل `entity_updated`. **العرض/التنزيل**: `/audit/exceptions/<pk>/evidence/view/`
  يسجّل `exception_evidence_viewed` (governance 0007).

### Finding — القيم الرقابية القياسية
| الحقل | الملاحظة |
|---|---|
| Finding | العنوان — يُقترح تلقائياً `ت-نوع` عند الإنشاء من استثناء |
| Criteria | المعيار — يُعبّأ مسبقاً من `test.rule_text` |
| Condition | الوضع الفعلي — يُعبّأ مسبقاً من `explanation` |
| Impact | الأثر (نص حر — **بدون نسب مخترعة**) |
| Cause | **يُقبل فقط مع `cause_supported=True`** (Form clean — خطأ عربي صريح) |
| Risk Level | High/Medium/Low فقط — **افتراضياً أخطر استثناء مرتبط** (عدّل يدوياً) |
| Recommendation | التوصية |
| Management Action | إجراء الإدارة (يُترك فارغاً ثم يُستكمل) |
| Status | مفتوح / قيد المعالجة / مُغلق + status_note |

- **Risk**: مصفوفة 3×3 فقط — أثر المبلغ × شدة الخلل (RR-01..RR-06 من `risk_rules.md`) —
  **لا AI/ML ولا تقييم آلي مخفي**؛ Risk على Finding يُورَّث من أخطر استثناء وقت الإنشاء
  كنقطة بداية معقولة ثم مسؤولية المدقّق.
- **الترقيم**: `F-YYYY-NNNNN` (`next_finding_code`) — سلسلة مستقلة عن `AR-`.
- **الترابط**: M2M ↔ الاستثناءات — من صفحة الاستثناء: ① المصدر ← ② الاختبار ←
  ③ Finding (زر "إنشاء Finding" يعبّأ النموذج مسبقاً ويُظهر الأصناف/المخاطر).

### صلاحيات (K3 — **الكتالوج يبقى 30**)
لا أكواد جديدة — إعادة استخدام: `audit.view` (Hub), `exceptions.view` (التفاصيل/العرض),
`exceptions.manage` (رفع الدليل), `findings.view` (القائمة/التفصيل)،
`findings.manage` (إنشاء/تعديل). روابط URL جديدة: 8 → مجموع قواعد audit = 17.

### تنقّل المدقّق (مُتحقق منه في الاختبارات)
Dashboard(`/audit/`) → Exception → Source Transaction (مصروف/مشتريات) → Test
(`#T-XXX`) → Finding (سلسلة كاملة في الاتجاهين).

### migrations
`audit_register/0003` (auditor_action + evidence + AuditFinding) · `governance/0007`
(action = `exception_evidence_viewed`).

---

## PHASE 11 — لوحة المؤشرات التفاعلية (Interactive Dashboard)

**URL:** `/dashboard/` · namespace `dashboard:index` · صلاحية **`dashboard.view`**
(موجودة في المصفوفة المعتمدة — **الكتالوج ثابت30 كودًا، لا أكواد جديدة**).
التطبيق: `apps.analytics` (كانت placeholder فارغة — رُبطت الآن وصُحّح
`verbose_name` إلى «لوحة المؤشرات التحليلية»). الصفحة الرئيسية `/` لم تُمس
(حالة النظام العامة).

### الأسئلة الإحدى عشرة — كل إجابة من استعلام حي
| # | السؤال | المصدر الحي |
|---|---|---|
| 1 | ما Budget؟ (Effective Budget) | Sum مجموع أعمدة الشهور المختارة من سطور الموازنة **المعتمدة** (وفق نافذة الفترة) |
| 2 | ما Actual Spend؟ | Sum مصروفات **USD** داخل نافذة التاريخ المختارة |
| 3 | ما Variance؟ | `Effective − Actual` (يظهر أخضر/أحمر) |
| 4 | ما نسبة الاستخدام؟ | `Actual / Budget ×100` — تقدّم شريط · «—» بلا موازنة |
| 5 | ما المصروفات خارج الموازنة؟ | مصروفات تركيبتها (إدارة×حساب) غير موجودة في أي سطر معتمد — KPI + جدول تفصيلي |
| 6 | ما الإدارات ذات الانحرافات؟ | رسم أعمدة (موازنة/تنفيذ) + جدول مع شارة «بلا انحراف» — مرتّب بـ \|Variance\| |
| 7 | ما الحسابات الأعلى صرفًا؟ | أعلى8 حسابات — رسم أفقي + قائمة مرقّمة |
| 8 | ما الاستثناءات؟ | KPI + توزيع الحالات + آخر6 استثناءات بروابط مباشرة لسجل الاستثناءات |
| 9 | ما مستويات المخاطر؟ | دونات High/Medium/Low + KPI High Risk — منطق تفسيري فقط **لا AI/ML** |
| 10 | ما نتائج Audit Tests؟ | **آخر جولة** (أو آخر جولة تحتوي الاختبار المفلتر) — دونات + جدول لكل اختبار |
| 11 | ما الاتجاه الشهري؟ | خط12 شهرًا: الموازنة مقابل التنفيذ (سنة الفiscal كاملة كسياق) |

**KPIs:** Effective Budget · Actual Expenses · Variance · Utilization % ·
Out-of-Budget Amount · Exception Count · High Risk Count · Procurement Exceptions.

### الفلاتر (كلها GET ومن قيم قاعدة حية)
- **الفترة (Period)** — فترة شهرية → نافذة المقاييس المالية (أعمدة mXX + نطاق التاريخ).
- **الإدارة / الحساب / التصنيف** — تؤثر على المقاييس المالية ورسوم
  الإدارات/الحسابات/الاتجاه الشهري.
- **الخطر (Risk)** + **الاختبار (Test)** — تؤثران على استثناءات/نتائج الاختبارات.
  قرار تصميم معلن: فلتر الفترة **مالي** (تاريخ المعاملات) ولا يُخلط مع تاريخ رصد
  الاستثناءات؛ الاستثناءات لا تملك مفتاح إدارة/حساب مباشر فلا تتأثر بتلك الفلاتر.

### الرسوم التفاعلية
Chart.js4 (CDN) — tooltips/legends تفاعلية: خط اتجاه شهري، أعمدة إدارات،
أفقية حسابات، دونات مخاطر، دونات نتائج — **كل سلاسلها من `charts` dict محسوب
وقت الطلب** — `json_script` آمن — لا قيمة مدمجة في القالب.

### تحقق شرط التوقف
اختبار `DataChangeTests.test_new_expense_changes_kpis_and_charts`: إضافة مصروف
777 → Actual4000→4777 وسلسلة أبريل في الاتجاه ورسم الإدارات تتغير فورًا؛
وجولة محرك جديدة → مؤشرات نتائج الاختبارات تتغير.

### migrations
لا (بدون نماذج جديدة) — `config/urls.py` + قاعدة `dashboard:index` في
`URL_PERMISSIONS` فقط.

---

## PHASE 12 — نظام التقارير + المرفقات + تتبّع العمليات الحساسة

**URL:** `/reports/` (namespace `reports`) — **الكتالوج ثابت30** (إعادة استخدام
`reports.view` للعرض و`reports.generate` للتصدير — الإدارة لديها view فقط فلا تصدّر).

### التقارير التسعة (كلها registry-driven من `apps/reports/builders.py`)
| # | Slug | المحتوى |
|---|---|---|
| 1 | budget-vs-actual | إدارة×حساب: موازنة/تنفيذ/انحراف/استخدام |
| 2 | variance | انحراف شهري (إدارة×حساب×شهر) مرتب بـ\|Variance\| مع الحالة |
| 3 | out-of-budget | مصروفات بلا تركيبة معتمدة (تقرير مفصّل) |
| 4 | expense-analysis | تجميع: عدد/إجمالي/متوسط/أعلى حسب الإدارة والحساب والتصنيف |
| 5 | procurement-exceptions | استثناءات مصدرها المشتريات مع مرجع العملية |
| 6 | test-results | نتائج كل الجولات: ناجح/مُعلَّم/فاشل + سجلات |
| 7 | exception-register | السجل الكامل مع ربط لكل استثناء |
| 8 | risk-report | توزيع High/Medium/Low على الاستثناءات والنتائج — **لا AI/ML** |
| 9 | findings | النتائج والتوصيات مع Management Action وربط |

- **كل تقرير:** فلاتر مصرّحة له فقط (period/department/account/category/risk/test
  حسب الحاجة) · نافذة تاريخ ظاهرة · ملخّص KPIs · **🖨 Print** (نافذة المتصفح) و
  **حفظ PDF عبر Print CSS** (`.print-only` header + `@media print` في app.css
  يخفي التنقل/الأزرار ويثبّت رأسًا: النظام/المُعدّ/الوقت/الفلاتر/عدد السطور) ·
  **CSV** (UTF-8+BOM ليفتح Excel بالعربية) و**XLSX** (openpyxl، خلايا رقمية
  حقيقية) — التصدير مسجّل `report_exported` (منفّذ + صيغة + عدد سطور + فلاتر).
- HTML وCSV وXLSX تأتي **من نفس البناء الحي** (`columns/rows/summary`) — لا أرقام
  ثابتة في أي قالب.

### المرفقات (Attachment — `governance/0008`)
نموذج عام: ملف + عنوان + **كيان مرتبط** (مصروف/مشتريات/استثناء/نتيجة) +
**بيانات وصفية** (حجم، content-type، من رفعه، وقت الرفع).
- رفع `POST /audit-trail/attachments/upload/` (≤10MB، تحقق من وجود الكيان) —
  يسجّل `attachment_uploaded` (diff يحوي الرابط الوصفي).
- عرض `/attachments/<pk>/view/` (inline) وتنزيل `/download/` — يسجّلان
  `attachment_viewed` / `attachment_downloaded`.
- قسم المرفقات (list + نموذج رفع) مدمج في صفحات التفصيل الأربع عبر tag
  `{% attachment_section %}` — يظهر فقط لمن يملك `attachments.view`، والنموذج
  لمن يملك `attachments.manage` (المدقّق+المدير فقط).

### تتبّع العمليات الحساسة (Traceability — مُختبر في `governance/tests.py`)
كلها مسجّلة بمنفّذ (لقطة اسم) + وقت + كيان + diff/sctx (IP/UA حيث ينطبق):
Create/Update/Delete (`entity_*`) · Import (`data_imported`) · Run Audit Test
(`entity_created/updated audit_run`) · **Change Rule / Change Risk**
(`entity_updated audit_test` مع `rule_text` و`default_risk` قبل/بعد — **أُصلح
خلل تصويري**: لقطة `before` تؤخذ الآن قبل `form.is_valid()` لأن ModelForm
يعدّل الـ instance في `_post_clean`) · Create Finding (`entity_created
audit_finding`) · Change Status (استثناء/نتيجة `entity_updated`) ·
Login/security (`login`، `login_failed` — التتبّع عبر اسم المحاولة في diff،
`logout`) مع IP/UA.
- صفحة السجل `audit-trail/` حصلت على فلاتر (action/entity_type/actor).

### اختبارات
+30 (reports16 + governance14) → **المجموعة281/281**.

---

## PHASE 13 — Synthetic Training Dataset + Ground Truth + اختبارات آلية

**SYNTHETIC Declaration**: كل السجلات في `datasets/training.py` اصطناعية
بالكامل لأغراض التدريب — لا تمثل أي شركة أو جهة حقيقية، ولا تحوي أي بيانات
فعلية من أي صاحب عمل.

### مجموعة التدريب (Loader — idempotent)
`python manage.py load_training_dataset` يبني (ويعيد بناءً دون تضاعف):
- FY2026 + 12 فترة مفتوحة · 4 إدارات · 4 تصنيفات (PAYROLL مُضاف) · 5 حسابات ·
  4 موردين (**واحد معطّل عمدًا**) · 4 مستخدمين بالأدوار المعتمدة.
- ميزانية معتمدة بـ5 سطور (uniform) = **69,000** سنويًا.
- **43 مصروفًا** USD مُوازنة عمدًا (35 على تركيبات مُوازنة + 8 خارج
  الموازنة) · **9 سجلات مشتريات** (نظيفة ومُعلَّمة مقصودة) · **18 عرض سعر**.
- كل صف مُصمَّم ضد عتبات المحرك: نية كشف ( overrun/early/variance/بدون مرفق/
  غير معتمد/نقدي كبير/تكرار×2/مبلغ شاذ/تصنيف مشبوه/شراء بلا PO/تراخيص ناقصة…)
  مقابل ضوابط سلبية (near-miss) لا يجب أن تُعلَّم.

### Ground Truth (مُعلن مسبقًا)
`EXPECTED_EXCEPTIONS` = **28** مفتاح `(test_code, exception_type, subject)` —
مع `EXPECTED_PER_TEST` · `MUST_NOT_FLAG` (ضوابط نظيفة) · `TARGETED_NEGATIVES`
(سالبات موجَّهة) · `RISK_SPOT_CHECKS` · `RISK_COUNTS = {10 High, 11 Medium,
7 Low}`. الاختبار يقارن **تساويًا تامًا للوجهين**: استثناء ناقص **أو** علم زائد
= فشل، مع طباعة القائمتين الناقصة/الزائدة.

### الاختبارات الآلية (`audit_register/tests_dataset.py` — 53)
لا يكفي أن تعمل الصفحة — إثبات خوارزمي عبر 11 فئة: Loader/البنية · مصادقة
(دخول/خروج مسجَّل) · صلاحيات (كتالوج 30 + مصفوفة صفحات 200/403/302 + بوابات
الأفعال) · CRUD (إنشاء/تعديل مع diff قبل/بعد + رفض التكرار) · استيراد CSV
(2 صالح + 1 غير صالح + 1 مكرر) · حسابات يدوية (69,000 / 123,190 / −54,190 /
OOB 8 = 18,550 مقابل ORM واللوحة) · قواعد التدقيق (التساوي التام 28/28) ·
دورة حياة الاستثناء (open→acknowledged→resolved + RBAC) · المخاطر (6 نطاقات
من معاملات DB + توزيع 10/11/7) · التقارير (سجل 28 + CSV BOM + …) · استعلامات
اللوحة (KPI + فلاتر إدارة/فترة/خطر).

### النتيجة
**334/334 ناجح** (281 سابقًا + 53 جديدًا) — `manage.py check` نظيف.

---

## PHASE 14 — UX Review (مراجعة الواجهة كنظام مهني)

مراجعة تحليلية كاملة لـ45 قالبًا + CSS + الهوية مقابل 14 معيارًا (Arabic-first ·
RTL · Responsive · التنقل · المصطلحات · النماذج · رسائل التحقق · الحالات
الفارغة · حالات التحميل/الخطأ · الجداول · الفلاتر · اللوحة · التباين ·
الطباعة).

- **النتيجة:** 7 مطابق / 6 جزئيًا أو غير مطابق — سجل نتائج مرقّم
  **F-01..F-18** (P1/P2/P3) بالدليل والتقدير في
  `output/phase14_ux_review/UX_REVIEW.md`.
- **أُنفَّذ بأمر المرحلة:** (1) وسم الهوية
  «Professional Proof-of-Work / Training & Demonstration System» أصبح في تذييل
  كل صفحة عبر `SYSTEM_CONTEXT`؛ (2) حُذف ذكر Al-Waha من README الجذري —
  النظام وREADME نظيفان تمامًا.
- **وسم قائم مؤكَّد:** «Synthetic Training Data» في شريط كل صفحة + اللوحة +
  شارات الاختبارات + رؤوس الطباعة.
- **أعلى توصية (P1):** F-01 الاعتماد على CDN خارجي محجوب (Bootstrap/Chart.js)
  → تثبيت الأصول محليًا قبل أي عرض؛ تليه نصوص المرحلة القديمة في
  الرئيسية/الشريط/ملخص الموازنة (F-02..F-05).
- **لا تنفيذ لأي توصية أخرى** — الإصلاحات تنتظر أمرًا صريحًا.

---

## PHASE 15 — Release Candidate (من Development Build إلى RC)

**النشر الخارجي (GitHub / Base44 / أي منصة) ممنوع حتى أمر صريح.**

> **تصحيح 2026-10-02:** هذا وصف تاريخي لفحوص Phase 15، لا موافقة نشر. لا تُشغّل `load_training_dataset` في production؛ HSTS preload ينتظر مراجعة النطاق/الـTLS؛ وفحوص `check --deploy` السابقة لا تعني تحققًا من مزوّد الاستضافة. راجع PHASE 16 أدناه.

### فحوصات الإصدار (22 بندًا — التفصيل في `output/phase15_rc/RELEASE_CHECKLIST.md`)
- **التكامل**: المجموعة **334/334 OK** · سلامة قاعدة البيانات (161 قيدًا، 77
  FK، صفر أيتام) · الصلاحيات (كتالوج 30 + مصفوفات 200/403/302) · الاستيراد ·
  المحرك (Ground Truth 28/28) · اللوحة · التقارير (9 + CSV BOM/XLSX) ·
  المرفقات (42/42 ملفًا على القرص) · سجل التدقيق · معالجة الأخطاء.
- **الأمن والإعدادات**: `check --deploy` = **0 issues** مع الأعلام الكاملة ·
  `DEBUG=False` إجباري · `ALLOWED_HOSTS` إلزامي (fail-fast مُثبت) · **بوابة قوة
  SECRET_KEY جديدة ترفض Placeholder حتى من `.env`** · WhiteNoise +
  `collectstatic` (128 ملفًا/384 معالَجة) · وسائط عبر مسار الـproxy في
  الإنتاج · PostgreSQL حصريًا (D-01) باتصالات صحة.
- **التشغيل**: لا انحراف migrations (`makemigrations --check` صفر) ·
  **استراتيجية إعادة التحميل**: `migrate` → `load_training_dataset`
  (idempotent) → `createsuperuser` · **النسخ/الاستعادة**: `pg_dump -Fc` +
  أرشيف `media/` + `.env` بقناة منفصلة، والاستعادة عبر `pg_restore` (خطوات
  كاملة في الـChecklist) · تحديث README هذا.

### مقدّرات النشر (خلاصة)
نطاق خاص · Python 3.11 + PostgreSQL 16 بدور مخصص · `.env` إنتاجية (مفتاح
عشوائي ≥50 حرفًا + مضيفون + TLS أعلام) · `DJANGO_SETTINGS_MODULE=
config.settings.production` · gunicorn خلف proxy يوفر TLS و`/media/` ·
تثبيت أصول محلية بدل CDN ( KN-01 ) · نسخ احتياطي مجدول · بوابة: `check` +
`check --deploy` + `test` قبل أي رفع.

### Known Issues (لا تمنع RC)
CDN خارجي محجوب في بيئة العمل (Bootstrap/Chart.js) · نصوص مرحلية قديمة
(خطة UX F-01..F-18) · محفظة تحسينات UX (F-07..F-18) · لا فحص مرئي آلي
(لا chromium) · الوسائط في الإنتاج تحتاج مسار proxy.

## PHASE 16 — Production isolation and import/export hardening (2026-10-02)

This is a staged engineering tranche, **not a deployment or production-readiness
approval**. Existing workflows, RBAC codes, training rows and declared Ground
Truth were retained; no real institution data is introduced.

**Deployment model decision (2026-10-02):** one isolated installation per
customer/organization; this is not a shared multi-tenant service. Reuse the same
release across customers, but give each installation its own production
secrets, PostgreSQL database/roles, domain, private persistent media, and backup
and restore boundary. Do not copy one customer's records, credentials, or media
into another installation. Organization-level database ownership fields are
not in scope for this model.

**Current-instance provider intent (owner, 2026-10-02):** Manus for the existing
application copy and Supabase for its cloud PostgreSQL; the public Manus page
responded to a read-only check, but the exact deployed revision, Supabase project,
region, connection method, secret handling, backup policy, and provider settings
have not been independently verified. The published Supabase region list checked
on this date does not list a Middle East region; confirm the actual dashboard
region and whether the requirement is data residency or only user proximity
before loading any real organizational data. See
https://supabase.com/docs/guides/platform/regions.

### Implemented in code

- Split base/development/staging/production settings. Production-like settings
  fail closed on weak keys, wildcard/local hosts, missing/invalid PostgreSQL
  configuration, an environment/module mismatch, invalid migration selector,
  and disabled HTTPS redirect. TLS is required for PostgreSQL outside development;
  HSTS preload remains gated until the real domain and proxy are verified.
- Added the separate `MIGRATION_DATABASE_URL` opt-in for release migrations;
  web workers continue to use the runtime `DATABASE_URL`. Production rejects
  SQLite and any non-PostgreSQL engine.
- Tagged loader-created demo accounts, blocked their authentication in
  production (including Django admin), and prevented the synthetic-data loader
  from running in production. Staging requires explicit opt-in and an isolated DB.
- Added minimal `/health/live/` and token-gated `/health/ready/`; environment,
  database, Django-version and route-manifest diagnostics are restricted to
  development/authenticated contexts.
- Added bounded import validation: extension/signature matching, upload-size,
  row/column/PDF-page and XLSX expansion limits; SHA-256 duplicate detection
  backed by a partial unique DB constraint; owner-scoped import jobs; row locks
  around validation/confirmation/cancellation; and a commit-time recheck of
  period-posting permission. Original uploaded files remain retained.
- CSV/XLSX export strings beginning with formula syntax are neutralized while
  numeric values remain numeric. Audit context/diffs are scrubbed recursively;
  untrusted `X-Forwarded-For` is ignored in favor of transport `REMOTE_ADDR`.
- Removed migration, training seeding and runtime static collection from the
  Docker web command. Static files are collected at build; the Docker worker runs
  unprivileged; migration is a separate release action. The Render blueprint has
  auto-deploy disabled. These deployment definitions have not been tested on the
  provider.

### Local verification (2026-10-02)

- `manage.py check`: clean; `makemigrations --check --dry-run`: no model drift;
  migration `imports.0002` applied on a disposable local PostgreSQL instance.
- Full local suite: **353/353 passed**. Existing Ground Truth data and expected
  result sets were not edited.
- Negative production-settings checks rejected wildcard hosts, weak keys,
  SQLite, disabled HTTPS redirect, environment/settings-module mismatch,
  invalid/missing migration selector and invalid HSTS preload. A valid sample was accepted;
  a URL requesting `sslmode=disable` was forced to `sslmode=require`.
- `check --deploy` exited successfully with the expected HSTS warning W004
  (`SECURE_HSTS_SECONDS=0` pending domain/TLS review). A cold `collectstatic`
  run copied 132 assets and post-processed 394; a later repeat found 132
  unmodified and processed 366, with no failure.
- Evidence checksum verification and `git diff --check` are reported at the end
  of this tranche. None of these local checks replaces provider verification.

### Still unverified / not completed

- Repeat migrations and the unchanged Ground Truth suite on the selected managed
  PostgreSQL provider; verify TLS, row-lock semantics, network/proxy trust and
  host-specific configuration.
- Current instance (Manus + Supabase): verify the served revision, secret/runtime
  configuration, PostgreSQL connection mode/TLS, private persistent media, and
  backup/restore. The current project region is not verified; the published
  Supabase region list does not show a Middle East option.
- Future customer copies may use other hosts, but each still needs its own app,
  database/roles, secrets, domain, private media, and backup/restore path.
  Per-user import privacy is not a substitute for these deployment boundaries.
- Select and test persistent private media storage, malware scanning, retention,
  backup and restore, and measured RPO/RTO. Current FileSystemStorage may be
  local/ephemeral on hosted platforms.
- Establish production administrator bootstrap and exact role policy. Existing
  migration seeds for RBAC/catalog/test definitions were deliberately preserved;
  the synthetic loader remains blocked in production.
- Run `check --deploy` with the real host, trusted origins, HSTS decision and
  proxy behavior. Do not infer readiness from unit tests alone.
- No deployment, push, merge or provider-side action has been performed.
