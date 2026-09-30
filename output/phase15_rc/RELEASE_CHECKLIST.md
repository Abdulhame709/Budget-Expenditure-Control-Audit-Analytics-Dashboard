# PHASE 15 — Release Checklist (Release Candidate)

**التاريخ:** 2026-09-30 · **الهدف:** تحويل النظام من Development Build إلى
**Release Candidate** · **النشر الخارجي (GitHub / Base44 / أي منصة) ممنوع
صراحةً حتى أمر صريح من المالك.**

الحالة: ✅ منفَّذ · ⚠️ منفَّذ مع ملاحظات · ⏸️ معلَّق بقرار/أمر

---

## أ) فحوصات التكامل والسلامة (البنود 1–10)

| # | البند | التنفيذ والدليل | الحالة |
|---|---|---|---|
| 1 | Full integration test | `manage.py test` الكامل: **334/334 OK** (auth · permissions · CRUD · imports · calculations · audit rules · exceptions · risk · reports · dashboard · governance · reference · budget · procurement · config) | ✅ |
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
| 11 | Security baseline review | `check --deploy` **= 0 issues** مع الأعلام الكاملة · Middlewares: Security/CSRF/XFrame/AccessControl · مدقّق كلمات مرور Django · بوابات صلاحيات على مستوى الصفحة والفعل · لا صلاحيات مجهولة (30 رمزًا مثبّتة) | ✅ |
| 12 | Environment configuration | `.env` (غير مُرتبَط بـGit — مُتحقق في `.gitignore`) · `.env.example` محدَّث بقسم إنتاج كامل · إعدادات ثلاثية: base/development/production | ✅ |
| 13 | SECRET_KEY / secrets | قاعدة: المفتاح من البيئة · **فجوة أُغلقت في هذه المرحلة**: بوابة قوة ترفض القيم الرمزية (`change-me…`/`django-insecure`/طول أقل من 50) حتى لو جاءت من `.env` — مُثبت بتجربة سالبة (رفض) وموجبة (قبول) · مولّد مفتاح موثّق في `.env.example` | ✅ |
| 14 | DEBUG=False production | `production.py` تفرض `DEBUG=False` دائمًا · دليل: DEVELOPMENT=True / PRODUCTION=False · `DJANGO_DEBUG` الميت أُزيل من المثال | ✅ |
| 15 | ALLOWED_HOSTS | إنتاج: فارغ = `ImproperlyConfigured` (مُثبت) · تعدد مضيفين بفواصل · تطوير `["*"]` مقصور على التطوير | ✅ |
| 16 | Static files | WhiteNoise + `CompressedManifestStaticFilesStorage` · `collectstatic` = **128 ملفًا (384 post-processed)** دون خطأ · مسارات `/static/` · **ملاحظة KN-01**: Bootstrap/Chart.js خارجية (CDN) | ⚠️ |
| 17 | Media configuration | `MEDIA_ROOT/URL` · التقديم في التطوير عبر `settings.DEBUG` فقط · إنتاج يحتاج مسار وسائط من الـproxy (مُوثّق في مقدّرات النشر) · رفع ≤10MB مُتحقَّق | ⚠️ |
| 18 | PostgreSQL production readiness | PostgreSQL حصريًّا (D-01: لا SQLite — `DATABASE_URL` إلزامي ويُفشل الإقلاع) · `conn_max_age=600` + `conn_health_checks=True` · دور/قاعدة مخصّصة · pg_hba/TLS = مقدّر نشر | ✅ |

## ج) التشغيل والمستندات (البنود 19–22)

| # | البند | التنفيذ والدليل | الحالة |
|---|---|---|---|
| 19 | Migration verification | `showmigrations`: **0 معلَّق** (كلها `[X]`) · `makemigrations --check --dry-run` = **No changes detected** (لا انحراف بين النماذج وبنية القاعدة) | ✅ |
| 20 | Seed/reseed strategy | ثلاثة طبقات: (1) `migrate` → كتالوجات RBAC + 14 اختبارًا رقابيًا (من مigrations — لا يدوي)؛ (2) `manage.py load_training_dataset` (idempotent — حذف/إعادة بالفاتورة الاصطناعية) للمجموعة التدريبية؛ (3) مستخدمو التشغيل: `createsuperuser` + ربط أدوار عبر `UserRole` (مستخدمو `ds_*` يأتيان من المحمّل). **إعادة كاملة**: migrate → load_training_dataset → createsuperuser | ✅ |
| 21 | Backup/restore guidance | **نسخة**: `pg_dump -Fc -d audit_budget_system -f audit_$(date +%F).dump` + أرشيف `media/` + حفظ `.env` (أسرار) بقناة منفصلة · **استعادة**: `createdb` → `pg_restore -d audit_budget_system audit_….dump` + فك `media/` · جدولة cron/systemd + نسخة خارج المضيف · اختبار استعادة ربع سنوي | ✅ وُثِّق |
| 22 | README update | قسم **PHASE 15 — Release Candidate** أُضيف إلى `system/README.md` (ملخّص الفحوصات + مقدّرات النشر + الاستراتيجيات) | ✅ |

---

## د) مقدّرات النشر (Deployment Prerequisites)

1. **مضيف + نطاق** خاص بالنظام (لا مشاركة نطاق عام أحادي).
2. **Python 3.11 + PostgreSQL 16** منفصل: دور/قاعدة/`pg_hba` + TLS، وصول عبر `DATABASE_URL`.
3. **`.env` إنتاجية** (خارج Git): `DJANGO_SECRET_KEY` عشوائي ≥50 حرفًا · `DJANGO_ALLOWED_HOSTS` (نطاقات) · `DATABASE_URL` · أعلام TLS (`DJANGO_SECURE_SSL_REDIRECT/HSTS…`) · `DJANGO_CSRF_TRUSTED_ORIGINS` عند الحاجة.
4. `DJANGO_SETTINGS_MODULE=config.settings.production`.
5. خطوات الإصدار: `migrate` → `collectstatic --noinput` → `load_training_dataset` (بيانات التدريب) → `createsuperuser`.
6. **خادم WSGI** (gunicorn) خلف **reverse proxy** (nginx/Caddy) يمنح TLS + `X-Forwarded-Proto` + مسار `/media/` للوسائط + (اختياري) تخطي WhiteNoise لـ`/static/`.
7. تثبيت الأصول محليًا (KN-01) أو ضمان وصول إلى jsdelivr.
8. نسخ احتياطي مجدول (البند 21) + تدوير سجلات (مُفعّل: RotatingFileHandler 2MB×5).
9. بوابة إصدار آلية: `manage.py check` + `check --deploy` + `test` (334) قبل أي رفع.
10. **عدم النشر لأي منصة خارجية بدون أمر صريح.**

## هـ) Known Issues (مُفهرسة — لا تمنع RC لكن تُدار)

| ID | الموضوع | الأثر |
|---|---|---|
| KN-01 | **CDN خارجي** (Bootstrap RTL + Chart.js من jsdelivr) محجوب في بيئة العمل — صفحات بلا تنسيق/مخططات دون إنترنت (F-01 من مراجعة UX) | عرض/تشغيل بلا اتصال · يُفضَّل تثبيت محلي قبل الإصدار النهائي |
| KN-02 | نصوص مرحلية قديمة في الرئيسية/الشريط/ملخص الموازنة (F-02..F-05) | مظهر غير مهني — خطة الإصلاح في وثيقة UX |
| KN-03 | محفظة UX (F-07..F-18): حالات تحميل · pagination · لفّ جداول · توحيد «تشغيلات/جولة» · IA التنقل | تحسينات — بأمر منفصل |
| KN-04 | الوسائط لا تُقدَّم إلا عبر DEBUG أو مسار proxy في الإنتاج | يتطلب إعداد nginx (مقدّر 6) |
| KN-05 | لا فحوص مرئية/e2e آلية (لا chromium في البيئة) — التغطية HTML/ORM/HTTP عبر Django tests | مقبول مع تحفّظ |
| KN-06 | `.env` التطوير الحية تحوي Placeholder للمفتاح — مقبول للتطوير فقط (الإنتاج يرفضه الآن صراحةً) | صفر أثر على الإنتاج |

## و) Blockers

| ID | البند | التفاصيل |
|---|---|---|
| B-01 | تثبيت أصول محلية (تصحيح KN-01) | تنزيل jsdelivr **محجوب في هذه البيئة** → لا يمكن جلب نسخ Bootstrap/Chart.js من هنا؛ يلزم قناة مصرّح بها أو مصدر pip في مرحلة إصلاح منفصلة |
| B-02 | النشر الخارجي | **ممنوع بأمر المالك** (GitHub/Base44/أي منصة) — ليس عطلًا تقنيًا بل قرار مُطبَّق: لا push تم ولم يُنفَّذ |

---

*مخرج PHASE 15 — يُعاد تحديث هذا الملف عند كل بوابة إصدار. توقّف بعد التقرير النهائي.*
