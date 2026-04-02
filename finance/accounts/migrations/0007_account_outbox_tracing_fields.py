from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_account_invitation_and_fallback"),
    ]

    operations = [
        migrations.AddField(
            model_name="domaineventoutbox",
            name="causation_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="correlation_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="request_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="last_publish_duration_ms",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="last_publish_finished_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="last_publish_result",
            field=models.CharField(
                choices=[("idle", "Idle"), ("running", "Running"), ("success", "Success"), ("failed", "Failed")],
                default="idle",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="last_publish_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="domaineventoutbox",
            name="last_publisher",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddIndex(
            model_name="domaineventoutbox",
            index=models.Index(fields=["correlation_id"], name="accoutbox_corr_idx"),
        ),
        migrations.AddIndex(
            model_name="domaineventoutbox",
            index=models.Index(fields=["request_id"], name="accoutbox_req_idx"),
        ),
    ]
