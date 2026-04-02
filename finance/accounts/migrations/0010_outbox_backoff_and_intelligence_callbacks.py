from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_account_intelligence_dispatch_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="domaineventoutbox",
            name="dead_letter_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="dead_lettered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="last_backoff_seconds",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="accountintelligencedispatchstate",
            name="last_error_message",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="accountintelligencedispatchstate",
            name="last_failed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="accountintelligencedispatchstate",
            name="last_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="domaineventoutbox",
            index=models.Index(fields=["status", "next_attempt_at"], name="accounts_out_status_9b4b93_idx"),
        ),
    ]
