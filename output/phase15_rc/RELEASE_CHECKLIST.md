# PHASE 15 — Release Checklist (Release Candidate)

**التاريخ:** 2026-09-30 · **الهدف:** تحويل النظام من Development Build إلى
**Release Candidate** · **كان النشر الخارجي ممنوعًا خلال Phase 15؛ لاحقًا دُمجت
تغييرات Phase 16 في GitHub `main` عبر PR #4 بتاريخ 2026-10-02. لا توجد موافقة
نشر إنتاجي أو مطابقة مثبتة بين `main` ورابط العرض.**

الحالة: ✅ منفَّذ · ⚠️ منفَّذ مع ملاحظات · ⏸️ معلَّق بقرار/أمر

> **تصحيح تاريخي (2026-10-02):** هذه القائمة توثّق فحوص Phase 15 بتاريخها،
> وليست موافقة نشر أو إثباتًا على مزوّد الاستضافة. Phase 16 يضيف عزل البيئة
> وإعدادات staging/production وإجراءات release منفصلة؛ `load_training_dataset`
> ممنوع في production. التحقق المحلي الحديث يُسجّل في `system/README.md`؛
> `check --deploy` الحالي يُبقي `SECURE_HSTS_SECONDS=0` عمدًا؛ التشغيل المحلي يُظهر W004 بشأن HSTS. لم تُختبر إعدادات المزود.
> النسخ/الاستعادة، المضيف وTLS والـproxy والأقفال على المزوّد ما زالت غير
> مختبرة. حدث push/merge إلى GitHub لاحقًا؛ نشر نسخة `main` نفسها على مزوّد
> التطبيق ما زال غير متحقق.

---

## أ) فحوصات التكامل والسلامة (البنود 1–10)

| # | البند | التنفيذ والدليل | الحالة |
|---|---|---|---|
| 1 | Full integration test | تشغيل Phase 15 التاريخي: **334/334 OK**. خط الأساس المحلي الأحدث الموثق بعد Phase 16: **353/353 OK** (auth · permissions · CRUD · imports · calculations · audit rules · exceptions · risk · reports · dashboard · governance · reference · budget · procurement · config) | ✅ |
| 2 | Database integrity checks | 161 قيدًا في public في `pg_constraint` (20 Check + 77 FK + 35 PK + 29 Unique) · مسح أيتام FK عبر كل العلاقات السبع = **NONE** · `manage.py check` نظيف · `BudgetLine.annual = Σmonths` مضمون بقيد DB | ✅ |
| 3 | Permission checks | كتالوج **30** صلاحية + `URL_PERMISSIONS` كلها داخل الكتالوج · مصفوفة صفحات 200/403/302 + بوابات الأفعال · RBAC لكل الأدوار الأربعة (tests_dataset + tests الوحدات) | ✅ |
| 4 | Import checks | تدفق كامل: رفع → استخراج → مطابقة → تحقق (2 صالح/1 غير صالح/1 مكرر) → تأكيد ذرّي → سجل `data_imported` + RBAC (tests_dataset.ImportTests + 27 اختبار PHASE 8) | ✅ |
| 5 | Audit Engine checks | تشغيل الـ14 اختبارًا → **28 استثناءً = Ground Truth مُعلن مسبقًا (تساوي تام للوجهين)** · `tests_fail = 0` · عدّادات `records_checked` · عتبات من DB | ✅ |
| 6 | Dashboard checks | KPIs حية من ORM: 69,000 / 123,190 / −54,190 / OOB 8=18,550 · فلاتر إدارة/فترة/خطر · توزيع المخاطر 10/11/7 | ✅ |
| 7 | Reports checks | 9 تقارير · سجل الاستثناءات 28 سطرًا + ملخصات مطابقة · CSV بـBOM + XLSX · RBAC للتصدير | ✅ |
| 8 | Attachment checks | رفع/عرض/تنزيل بأمر صحيح + RBAC (PHASE 12) · سلامة ملفات المجموعة: **42 مرفقًا غير فارغ / 42 ملفًا على القرص** | ✅ |
| 9 | Audit Trail checks | تسجيل login/login_failed/logout · entity_created/updated بـdiff قبل/بعد · data_imported · report_exported · attachment_* · فلاتر الصفحة (governance tests 14) | ✅ |
| 10 | Error handling | صفحات 403/404/500 عربيّة ومتسقة (`handler403/404/500`) · رسائل نماذج عربية · فشل المحرك/الاستيراد يُعرض كحالة · fail-fast للإعدادات (أدلة سالبة أدناه) | ✅ |

## ب) الأمن والإعدادات (البنود 11–18)

| # | البند | التنفيذ والدليل | الحالة |
|---|---|---|---|
| 11 | Security baseline review | فحص Phase 15 بـHSTS preload كامل كان تاريخيًا بلا issues؛ إعداد Phase 16 يبقي `SECURE_HSTS_SECONDS=0` حتى مراجعة النطاق والـTLS، ويظهر W004 في التشغيل المحلي. راجع إعداد المزود قبل أي release. | ⚠️ |
| 12 | Environment configuration | `.env` غير مُرتبط بـGit · base/development/staging/production منفصلة مع fail-closed checks محلية؛ إعدادات مزوّد الاستضافة والنطاق لم تُتحقّق. | ⚠️ |
| 13 | SECRET_KEY / secrets | قاعدة: المفتاح من البيئة · **فجوة أُغلقت في هذه المرحلة**: بوابة قوة ترفض القيم الرمزية (`change-me…`/`django-insecure`/طول أقل من 50) حتى لو جاءت من `.env` — مُثبت بتجربة سالبة (رفض) وموجبة (قبول) · مولّد مفتاح موثّق في `.env.example` | ✅ |
| 14 | DEBUG=False production | `production.py` تفرض `DEBUG=False` دائمًا · دليل: DEVELOPMENT=True / PRODUCTION=False · `DJANGO_DEBUG` الميت أُزيل من المثال | ✅ |
| 15 | ALLOWED_HOSTS | إنتاج: فارغ = `ImproperlyConfigured` (مُثبت) · تعدد مضيفين بفواصل · تطوير `["*"]` مقصور على التطوير | ✅ |
| 16 | Static files | WhiteNoise + `CompressedManifestStaticFilesStorage` · `collectstatic` = **128 ملفًا (384 post-processed)** دون خطأ · مسارات `/static/` · **ملاحظة KN-01**: Bootstrap/Chart.js خارجية (CDN) | ⚠️ |
| 17 | Media configuration | `MEDIA_ROOT/URL` · التقديم في التطوير عبر `settings.DEBUG` فقط · إنتاج يحتاج مسار وسائط من الـproxy (مُوثّق في مقدّرات النشر) · رفع ≤10MB مُتحقَّق | ⚠️ |
| 18 | PostgreSQL production readiness | PostgreSQL حصريًا وإعداد TLS/URL مضبوط محليًا؛ دور وقاعدة ومضيف `pg_hba` والـTLS على المزوّد لم تُتحقّق بعد. | ⚠️ |

## ج) التشغيل والمستندات (البنود 19–22)

| # | البند | التنفيذ والدليل | الحالة |
|---|---|---|---|
| 19 | Migration verification | `showmigrations`: **0 معلَّق** (كلها `[X]`) · `makemigrations --check --dry-run` = **No changes detected** (لا انحراف بين النماذج وبنية القاعدة) | ✅ |
| 20 | Seed/reseed strategy | PHASE 15 وصفت استراتيجية demo تاريخيًا. PHASE 16 تمنع loader في production؛ dev مسموح وstaging يتطلب opt-in وقاعدة معزولة. Production: migrations + مستخدم مسمّى يُنشأ منفصلًا، بلا حسابات demo. تحقق bootstrap على المزوّد معلّق. | ⚠️ |
| 21 | Backup/restore guidance | أوامر `pg_dump -Fc`/`pg_restore` وتصدير media/الأسرار بقناة منفصلة مُوثّقة تاريخيًا فقط؛ لا توجد نسخة مجدولة أو تجربة استعادة موثقة على المزوّد. RPO/RTO والاحتفاظ ما زالت تتطلب قرارًا وقياسًا. | ⚠️ |
| 22 | README update | قسم **PHASE 15 — Release Candidate** أُضيف إلى `system/README.md` (ملخّص الفحوصات + مقدّرات النشر + الاستراتيجيات) | ✅ |

---

## د) مقدّرات النشر (Deployment Prerequisites)

1. **مضيف + نطاق** خاص بالنظام (لا مشاركة نطاق عام أحادي).
2. **Python 3.11 + PostgreSQL 16** منفصل: دور/قاعدة/`pg_hba` + TLS، وصول عبر `DATABASE_URL`.
3. **`.env` إنتاجية** (خارج Git): `DJANGO_SECRET_KEY` عشوائي ≥50 حرفًا · `DJANGO_ALLOWED_HOSTS` (نطاقات) · `DATABASE_URL` · أعلام TLS (`DJANGO_SECURE_SSL_REDIRECT/HSTS…`) · `DJANGO_CSRF_TRUSTED_ORIGINS` عند الحاجة.
4. `DJANGO_SETTINGS_MODULE=config.settings.production`.
5. خطوات الإصدار بعد الموافقة: جمع static عند build → مهمة release منفصلة بـ`DJANGO_USE_MIGRATION_DATABASE=true` لترحيل DB → bootstrap لمستخدم إنتاج مسمّى؛ لا تشغّل `load_training_dataset` في production.
6. **خادم WSGI** (gunicorn) خلف **reverse proxy** (nginx/Caddy) يمنح TLS + `X-Forwarded-Proto` + مسار `/media/` للوسائط + (اختياري) تخطي WhiteNoise لـ`/static/`.
7. تثبيت الأصول محليًا (KN-01) أو ضمان وصول إلى jsdelivr.
8. نسخ احتياطي مجدول (البند 21) + تدوير سجلات (مُفعّل: RotatingFileHandler 2MB×5).
9. بوابة إصدار آلية: `manage.py check` + `check --deploy` + `test` (الخط الأساس الموثق: 353) قبل أي إصدار لاحق.
10. **عدم النشر لأي منصة خارجية بدون أمر صريح.**

## هـ) Known Issues (مُفهرسة — لا تمنع RC لكن تُدار)

| ID | الموضوع | الأثر |
|---|---|---|
| KN-01 | **CDN خارجي** (Bootstrap RTL + Chart.js من jsdelivr) كان محجوبًا في بيئة Phase 15؛ روابط الأصول الثلاثة أعادت HTTP 200 في 2026-10-02، لكنها تظل تبعية شبكة خارجية | عرض/تشغيل بلا اتصال · يُفضَّل تثبيت محلي قبل الإصدار النهائي |
| KN-02 | نصوص مرحلية قديمة في الرئيسية/الشريط/ملخص الموازنة (F-02..F-05) | مظهر غير مهني — خطة الإصلاح في وثيقة UX |
| KN-03 | محفظة UX (F-07..F-18): حالات تحميل · pagination · لفّ جداول · توحيد «تشغيلات/جولة» · IA التنقل | تحسينات — بأمر منفصل |
| KN-04 | الوسائط لا تُقدَّم إلا عبر DEBUG أو مسار proxy في الإنتاج | يتطلب إعداد nginx (مقدّر 6) |
| KN-05 | لا فحوص مرئية/e2e آلية (لا chromium في البيئة) — التغطية HTML/ORM/HTTP عبر Django tests | مقبول مع تحفّظ |
| KN-06 | `.env` التطوير الحية تحوي Placeholder للمفتاح — مقبول للتطوير فقط (الإنتاج يرفضه الآن صراحةً) | صفر أثر على الإنتاج |

## و) Blockers

| ID | البند | التفاصيل |
|---|---|---|
| B-01 | تثبيت أصول محلية (تصحيح KN-01) | لم يعد الوصول الحالي إلى jsdelivr محجوبًا (HTTP 200 في 2026-10-02)، لكن قرار vendoring المحلي لم يُنفّذ بعد |
| B-02 | النشر الخارجي | تم push/merge إلى GitHub `main` لاحقًا عبر PR #4؛ نشر نسخة `main` نفسها على مزوّد التطبيق وإثبات مطابقتها لرابط العرض ما زالا معلّقين |

---

*مخرج PHASE 15 — يُعاد تحديث هذا الملف عند كل بوابة إصدار. توقّف بعد التقرير النهائي.*
