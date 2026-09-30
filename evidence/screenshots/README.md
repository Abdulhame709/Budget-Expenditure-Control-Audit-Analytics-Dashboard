# Screenshots

المجلد المخصص **لقطات واجهة النظام** (UI screenshots) كدليل بصري في المستودع.

## الحالة الحالية

**فارغ — ولسبب مُوثَّق:** بيئة التطوير الحالية لا تضم متصفحًا (Chromium) ولا أتمتة مرئية،
لذلك لا يمكن التقاط لقطات حيّة من هنا (Known Issue **KN-05** في Release Checklist).
البدائل المتوفرة حاليًا:

- لقطات HTML الحيّة لمراحل التحقق: `output/phase10_evidence/` · `phase11_evidence/` · `phase12_evidence/`
- رسوم ومؤشرات التحقق: `../` (مجلد evidence: PNG + checksums)

## كيف يُعبَّأ (من بيئة بها متصفح)

```bash
# بعد تشغيل الخادم محليًا (system/):
python manage.py runserver
# ثم التقط شاشة للواجهات الرئيسية باسمين صناعيين:
#   01_dashboard_ar_rtl.png      — لوحة المؤشرات (RTL)
#  02_exception_register.png    — سجل الاستثناءات
#  03_report_print_view.png     — عرض تقرير قبل الطباعة
#  04_import_preview.png        — معاينة رفع ملف
# ارفعها هنا مع تحديث ../README.md
```

جميع اللقطات المستقبلية يجب أن تكون من البيانات الاصطناعية فقط (Synthetic notice).
