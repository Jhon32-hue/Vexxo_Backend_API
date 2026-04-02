from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_account_sync_runtime"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountIntelligenceDispatchState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pending_request", models.BooleanField(default=False)),
                ("request_count", models.PositiveIntegerField(default=0)),
                ("last_requested_at", models.DateTimeField(blank=True, null=True)),
                ("last_enqueued_at", models.DateTimeField(blank=True, null=True)),
                ("last_completed_at", models.DateTimeField(blank=True, null=True)),
                ("last_event_type", models.CharField(blank=True, default="", max_length=128)),
                ("last_source", models.CharField(blank=True, default="", max_length=128)),
                ("last_correlation_id", models.CharField(blank=True, default="", max_length=64)),
                ("last_task_name", models.CharField(blank=True, default="", max_length=255)),
                ("last_result", models.CharField(blank=True, default="", max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="account_intelligence_dispatch_state",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Account intelligence dispatch state",
                "verbose_name_plural": "Account intelligence dispatch states",
            },
        ),
        migrations.AddIndex(
            model_name="accountintelligencedispatchstate",
            index=models.Index(fields=["pending_request", "last_requested_at"], name="accounts_ai_pending_3c0e4d_idx"),
        ),
    ]
