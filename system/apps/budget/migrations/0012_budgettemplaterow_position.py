from django.db import migrations, models


def backfill_row_positions(apps, schema_editor):
    BudgetTemplateRow = apps.get_model("budget", "BudgetTemplateRow")
    rows = BudgetTemplateRow.objects.all().only("pk", "row_number")
    for row in rows.iterator():
        row.position = row.row_number
        row.save(update_fields=["position"])


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0011_backfill_template_runtime_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgettemplaterow",
            name="position",
            field=models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض"),
        ),
        migrations.RunPython(backfill_row_positions, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="budgettemplaterow",
            options={
                "ordering": ["sheet", "position", "row_number", "pk"],
                "verbose_name": "صف نموذج موازنة",
                "verbose_name_plural": "صفوف نماذج الموازنة",
            },
        ),
    ]
