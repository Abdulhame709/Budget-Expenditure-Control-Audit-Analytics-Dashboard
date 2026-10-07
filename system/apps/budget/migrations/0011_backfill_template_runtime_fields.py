from django.db import migrations


def backfill_template_runtime_fields(apps, schema_editor):
    BudgetTemplateRow = apps.get_model("budget", "BudgetTemplateRow")
    BudgetTemplateCell = apps.get_model("budget", "BudgetTemplateCell")

    rows = []
    for row in BudgetTemplateRow.objects.select_related("account__parent"):
        account = row.account
        if account is not None:
            if account.level == 5:
                row.main_account_id = account.pk
            elif account.level == 6:
                row.main_account_id = account.parent_id
                row.analytical_account_id = account.pk
            rows.append(row)
    if rows:
        BudgetTemplateRow.objects.bulk_update(
            rows, ["main_account", "analytical_account"],
        )

    BudgetTemplateCell.objects.filter(
        row__row_type="data",
        formula="",
    ).update(is_editable=True)


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0010_budget_template_runtime_fields"),
    ]

    operations = [
        migrations.RunPython(
            backfill_template_runtime_fields,
            migrations.RunPython.noop,
        ),
    ]
