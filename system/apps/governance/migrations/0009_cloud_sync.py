from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("governance", "0008_alter_auditlog_action_attachment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CloudSyncRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("running", "قيد التنفيذ"), ("completed", "مكتملة"), ("partial", "مكتملة مع تعارضات"), ("failed", "فشلت")], default="running", max_length=16)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error", models.TextField(blank=True)),
                ("started_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cloud_sync_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "cloud_sync_runs", "ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="CloudSyncRecordState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("model_label", models.CharField(max_length=120)),
                ("object_pk", models.CharField(max_length=128)),
                ("cloud_hash", models.CharField(max_length=64)),
                ("synced_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "cloud_sync_record_states",
                "constraints": [models.UniqueConstraint(fields=("model_label", "object_pk"), name="uq_cloud_sync_record_state")],
            },
        ),
    ]
