"""PHASE 9 — seed the 14 approved audit tests (reference: previous project's
docs/audit-tests.md + scripts/run_audit_tests.py).

Every threshold is declared as a Synthetic/Training Rule (P1–P9 were Synthetic
Policy Assumptions — NOT real client policy). Definitions + parameters live in
the DB and are editable from the UI (audit.rules.manage).
"""
from django.db import migrations

DECL = ("قاعدة تدريبية اصطناعية (Synthetic/Training Rule) — العتبات أدناه "
        "افتراضات تدريبية من المشروع السابق (P1–P9) وليست سياسة معتمدة من "
        "جهة حقيقية. ")

BANDS = {"a3": 10000, "a2": 2000}

TESTS = [
    # ---------------------------------------------------------------- budget
    dict(
        test_code="T-BUD-01", domain="budget",
        name="تجاوز الموازنة السنوي / الاستهلاك المبكر (Budget Overrun / Early Consumption)",
        objective="كشف التركيبات التي تجاوزت ميزانيتها السنوية أو استهلكت 100% قبل نهاية أكتوبر.",
        rule_text=DECL + "(Σ تنفيذ سنوي > ميزانية فعّالة وفرق > $500) أو (تراكمي حتى نهاية أكتوبر ≥ سنوي). التركيبة = (إدارة، حساب) في نسخة الموازنة المعتمدة. المصروفات بعملة الأساس USD فقط (لا سعر صرف في المخطط).",
        parameters={"synthetic_rule": True, "overrun_tolerance": 500,
                    "early_cutoff_month": 10, "currency": "USD",
                    "risk_bands": BANDS},
        data_source="budget_lines (approved version) + actual_expenses (USD)",
        expected_result="نحو نصف التركيبات فوق 100% بدرجات؛ نسبة صغيرة تصل 100% قبل أكتوبر.",
        exception_type="Annual Overrun / Early Consumption",
        default_risk="Medium",
        auditor_action="ربط التركيبة باستثناءاتها، تبرير من مدير الإدارة، مقترح إعادة توزيع أو تجميد.",
        engine_key="budget_overrun_early",
    ),
    dict(
        test_code="T-BUD-02", domain="budget",
        name="إنفاق خارج الموازنة (Out-of-Budget Expenditure)",
        objective="كشف مصروفات بلا أي تغطية موازنةية.",
        rule_text=DECL + "تركيبة (إدارة، حساب) غير موجودة في سطور الموازنة المعتمدة (join أيسر). مصروفات USD فقط.",
        parameters={"synthetic_rule": True, "currency": "USD",
                    "risk_bands": BANDS},
        data_source="actual_expenses ⟕ budget_lines (approved)",
        expected_result="وحدات معدودة فقط من المعاملات.",
        exception_type="Out of Budget",
        default_risk="High",
        auditor_action="تأكيد عدم إغفال بند موازنة، تفويض الصرف أو إدراجه في الموازنة القادمة.",
        engine_key="budget_coverage",
    ),
    dict(
        test_code="T-BUD-03", domain="budget",
        name="انحراف شهري غير عادي (Unusual Monthly Variance)",
        objective="كشف أشهر استهلكت بحد كبير موازنتها الشهرية.",
        rule_text=DECL + "تنفيذ شهر > 250% من ميزانية الشهر وفرق > $1,500 (P6). مصروفات USD فقط.",
        parameters={"synthetic_rule": True, "utilization_multiple": 2.5,
                    "excess_min": 1500, "currency": "USD",
                    "risk_bands": BANDS},
        data_source="actual_expenses (USD) مجمعة شهريًا + budget_lines (معدل m01..m12)",
        expected_result="نحو 5% من الأشهر — يستدعي فحص السبب لا مخالفة مؤكدة.",
        exception_type="Unusual Monthly Variance",
        default_risk="Low",
        auditor_action="فحص فواتير الشهر ومصروفاته، تقييم أثر التوقيت، اقتراح توزيع أفضل.",
        engine_key="monthly_variance",
    ),
    # ------------------------------------------------------------ procurement
    dict(
        test_code="T-PROC-01", domain="procurement",
        name="عروض أسعار غير كافية (Insufficient Quotations)",
        objective="قياس الالتزام بسياسة المنافسة (P1).",
        rule_text=DECL + "عدد العروض < 3 وقيمة السجل ≥ $1,000 (P1). السجلات الملغاة مستبعدة.",
        parameters={"synthetic_rule": True, "min_quotes": 3,
                    "min_amount": 1000, "risk_bands": BANDS},
        data_source="procurements + procurement_quotations",
        expected_result="نحو ربع العمليات — ضعف بنيوي في تطبيق السياسة.",
        exception_type="Insufficient Quotations",
        default_risk="Medium",
        auditor_action="طلب مستند المنافسة أو تبرير الشراء المباشر، مراجعة حكم السياسة.",
        engine_key="proc_min_quotes",
    ),
    dict(
        test_code="T-PROC-02", domain="procurement",
        name="مستندات مشتريات ناقصة — PO (Missing PO)",
        objective="اكتمال التوثيق: تفويض مسبق (P2).",
        rule_text=DECL + "أمر شراء فارغ وقيمة ≥ $500 (P2). حقل إثبات الاستلام غير متاح في المخطط الحالي — فحصه معطّل عبر المعامل check_receiving (لا يُفترض بيانات غير موجودة). السجلات الملغاة مستبعدة.",
        parameters={"synthetic_rule": True, "po_min_amount": 500,
                    "check_receiving": False, "risk_bands": BANDS},
        data_source="procurements",
        expected_result="نحو 10% من السجلات.",
        exception_type="Missing PO / Receiving Evidence",
        default_risk="Medium",
        auditor_action="طلب PO متأخر أو تبرير؛ طلب إثبات الاستلام ومطابقة الكمية عند توفر الحقل.",
        engine_key="proc_documents",
    ),
    dict(
        test_code="T-PROC-03", domain="procurement",
        name="موافقة غير مكتملة (Incomplete Approval)",
        objective="مشتريات لم يكتمل اعتمادها — المرفوض/الملغى ليس استثناءً (الضابط نجح).",
        rule_text=DECL + "الحالة ∈ {مسودة، بانتظار الاعتماد} — التحويل: draft/pending ≙ Pending Approval القديم، cancelled ≙ Rejected (ليس استثناءً).",
        parameters={"synthetic_rule": True,
                    "pending_statuses": ["draft", "pending"],
                    "risk_bands": BANDS},
        data_source="procurements",
        expected_result="نحو 5% من السجلات.",
        exception_type="Incomplete Approval",
        default_risk="Medium",
        auditor_action="استكمال الاعتماد أو الإلغاء؛ تحقق هل نُفذت فعليًا (استلام/دفع).",
        engine_key="proc_approval_pending",
    ),
    dict(
        test_code="T-PROC-04", domain="procurement",
        name="تعامل مع مورد غير نشط (Inactive Supplier)",
        objective="مشتريات من مورد حالته معطّلة في دليل الموردين.",
        rule_text=DECL + "حالة المورد الحالية ≠ نشط (join بمفتاح المورد وقت التشغيل) — يحتاج تأكيد التوقيت (ربما أُوقف بعد التعاقد).",
        parameters={"synthetic_rule": True, "risk_bands": BANDS},
        data_source="procurements ⟕ suppliers",
        expected_result="نحو 5–6% من المشتريات.",
        exception_type="Inactive Supplier",
        default_risk="Medium",
        auditor_action="تأكيد حالة المورد وقت التعاقد وسبب الإيقاف، مراجعة دفتر الموردين.",
        engine_key="proc_inactive_supplier",
    ),
    dict(
        test_code="T-PROC-05", domain="procurement",
        name="نمط شراء عالي القيمة بمنافسة غير كافية (High-Value Low Competition)",
        objective="نمط: قيمة كبيرة + ضعف منافسة (P9).",
        rule_text=DECL + "قيمة ≥ $10,000 وعدد العروض < 3 (P9). السجلات الملغاة مستبعدة.",
        parameters={"synthetic_rule": True, "high_value": 10000,
                    "min_quotes": 3, "risk_bands": BANDS},
        data_source="procurements + procurement_quotations",
        expected_result="مجموعة صغيرة ≈ 6% لكنها أكبر المبالغ — تستدعي فحصًا لا اتهامًا.",
        exception_type="High-Value Low Competition",
        default_risk="High",
        auditor_action="أولوية فحص: مستندات المنافسة والتسعير، مقابلة مسؤول المشتري.",
        engine_key="proc_high_value_low_comp",
    ),
    # ---------------------------------------------------------------- expense
    dict(
        test_code="T-EXP-01", domain="expense",
        name="مستند داعم ناقص أو مفقود (Missing Supporting Document)",
        objective="قياس قابلية التحقق من المصروفات.",
        rule_text=DECL + "بلا مرفق مساند (Doc_Status مشتق من وجود attachment في المخطط الحالي). حالة Partial غير قابلة للتمثيل — فحصها معطّل عبر check_partial (لا يُفترض بيانات). مصروفات USD فقط.",
        parameters={"synthetic_rule": True, "check_partial": False,
                    "currency": "USD", "risk_bands": BANDS},
        data_source="actual_expenses (attachment, USD)",
        expected_result="نحو 5% من المعاملات.",
        exception_type="Missing / Partial Supporting Document",
        default_risk="Medium",
        auditor_action="طلب المستند وإضافته للملف؛ إن تكرر: توصية إيقاف الصرف دون مستند.",
        engine_key="exp_supporting_docs",
    ),
    dict(
        test_code="T-EXP-02", domain="expense",
        name="استثناءات ضوابط الدفع (Payment Control Exceptions)",
        objective="اعتماد المدفوعات وطريقة التنفيذ — ضابطتان بهدف واحد.",
        rule_text=DECL + "(أ) مصروف غير معتمد (لا approved_by ولا مرجع اعتماد) أو (ب) دفع نقدي ≥ $5,000 (P4). النوع يُميَّز لكل استثناء. USD فقط.",
        parameters={"synthetic_rule": True, "large_cash": 5000,
                    "currency": "USD", "risk_bands": BANDS},
        data_source="actual_expenses (USD)",
        expected_result="نسبة دون الاعتماد + أقل من 1% نقدي كبير.",
        exception_type="Unapproved Payment / Large Cash Payment",
        default_risk="High",
        auditor_action="استكمال الاعتماد ومطابقة السند النقدي؛ مقترح رفع حد النقد.",
        engine_key="exp_payment_controls",
    ),
    dict(
        test_code="T-EXP-03", domain="expense",
        name="تكرار محتمل (Possible Duplicate Transaction)",
        objective="كشف احتمال الدفع المكرر — أعلى الأخطاء المالية المباشرة.",
        rule_text=DECL + "(مورد + مبلغ متطابقان وفرق ≤ 3 أيام) أو نفس رقم الفاتورة (≥ $100) (P8) — كل زوج استثناء واحد يشير للأصل والمكرر. USD فقط.",
        parameters={"synthetic_rule": True, "dup_days": 3,
                    "dup_min_amount": 100, "currency": "USD",
                    "risk_bands": BANDS},
        data_source="actual_expenses (USD)",
        expected_result="نحو 5 أزواج (3 بنفس الفاتورة).",
        exception_type="Possible Duplicate Payment",
        default_risk="High",
        auditor_action="مطابقة الفاتورة والتحويل؛ إن ثبت: طلب استرداد + فحص ضابط التكرار.",
        engine_key="exp_duplicates",
    ),
    dict(
        test_code="T-EXP-04", domain="expense",
        name="مبلغ غير معتاد (Unusual Amount)",
        objective="كشف مبالغ تتجاوز نظائرها في نفس الإدارة والحساب.",
        rule_text=DECL + "≥ $500 و ≥ 4× وسيط النظائر (إدارة، حساب) (P5). لا يوجد حقل PO على المصروف في المخطط الحالي — تُعامل كل المعاملات كبلا PO (مُعلن). USD فقط.",
        parameters={"synthetic_rule": True, "multiple": 4,
                    "floor_amount": 500, "currency": "USD",
                    "risk_bands": BANDS},
        data_source="actual_expenses (USD)",
        expected_result="نحو 1.5% من المعاملات — يستدعي فحص الطبيعة لا اتهامًا.",
        exception_type="Unusual Amount",
        default_risk="Medium",
        auditor_action="فحص المستند وطبيعة الباب، تأكيد عدم خطأ تصنيف أو خطأ إدخال.",
        engine_key="exp_unusual_amount",
    ),
    dict(
        test_code="T-EXP-05", domain="expense",
        name="تصنيف مشبوه (Suspicious Classification)",
        objective="كشف وصف يتعارض مع الفئة المصنّفة.",
        rule_text=DECL + "كلمات مفتاحية (مخزّنة في المعاملات keyword_map — قابلة للإدارة من DB) تدل على فئة ≠ الفعلية، مع استبعاد فئات محددة (PAYROLL). خريطة الكلمات تدريبية.",
        parameters={"synthetic_rule": True,
                    "keyword_map": {
                        "TRAVEL": ["hotel", "flight", "accommodation",
                                   "فندق", "سفر"],
                        "SUPPLIES": ["fuel", "diesel", "refueling", "tyres",
                                     "وقود"],
                        "SERVICES": ["software", "license", "cloud hosting",
                                     "training", "certification",
                                     "advertising", "campaign",
                                     "marketing agency", "exhibition"],
                    },
                    "exclude_category_codes": ["PAYROLL"],
                    "risk_bands": BANDS},
        data_source="actual_expenses + expense_categories",
        expected_result="أقل من 1% — نادر في بيانات سليمة.",
        exception_type="Suspicious Classification",
        default_risk="Medium",
        auditor_action="فحص طبيعة المعاملة، إعادة تصنيف عند الإثبات، إعادة احتساب أثر الفئة.",
        engine_key="exp_classification",
    ),
    dict(
        test_code="T-EXP-06", domain="expense",
        name="مشتريات بدون أمر شراء (Purchase without PO)",
        objective="كشف مشتريات نُفّذت عبر المصروفات تفاديًا للمشتريات.",
        rule_text=DECL + "وصف شرائي (كلمات purchase_keywords في المعاملات) وقيمة ≥ $1,000 (P2) وبدون «Payment for…». لا يوجد حقل PO على المصروف — كل المعاملات تُعامل كبلا PO (مُعلن). USD فقط.",
        parameters={"synthetic_rule": True,
                    "purchase_keywords": ["purchase", "laptops", "materials",
                                          "spare parts", "racking", "gifts",
                                          "equipment", "شراء", "أجهزة"],
                    "po_min_amount": 1000, "currency": "USD",
                    "risk_bands": BANDS},
        data_source="actual_expenses (USD)",
        expected_result="نحو 2.5% من المعاملات.",
        exception_type="Purchase without PO",
        default_risk="Medium",
        auditor_action="مطابقة بسجل المشتريات، تبرير أو رفض الصرف لاحقًا، تعزيز شرط PO.",
        engine_key="exp_purchase_no_po",
    ),
]


def seed_tests(apps, schema_editor):
    AuditTest = apps.get_model("audit_register", "AuditTest")
    for t in TESTS:
        AuditTest.objects.update_or_create(
            test_code=t["test_code"],
            defaults={**t, "is_active": True, "synthetic_rule": True,
                      "created_by": None, "updated_by": None},
        )


def unseed_tests(apps, schema_editor):
    AuditTest = apps.get_model("audit_register", "AuditTest")
    AuditTest.objects.filter(
        test_code__in=[t["test_code"] for t in TESTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("audit_register", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(seed_tests, unseed_tests),
    ]
