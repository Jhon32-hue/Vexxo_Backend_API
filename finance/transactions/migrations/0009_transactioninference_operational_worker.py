from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0008_transactioninference_request"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transactioninferencerequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "en cola"),
                    ("processing", "procesando"),
                    ("dispatch_failed", "despacho fallido"),
                    ("processing_stale", "procesamiento stale"),
                    ("transcription_failed", "transcripcion fallida"),
                    ("extraction_failed", "extraccion fallida"),
                    ("applied", "aplicada"),
                    ("partial", "parcial"),
                    ("dead_letter", "agotada"),
                    ("canceled", "cancelada"),
                ],
                db_index=True,
                default="queued",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="dispatch_attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="dispatch_backend",
            field=models.CharField(
                blank=True,
                choices=[("cloud_tasks", "cloud tasks"), ("local_worker", "worker local")],
                db_index=True,
                default="",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="last_dispatch_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="last_dispatch_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="last_dispatch_result",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="last_operational_issue",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="last_recovered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="local_worker_locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="local_worker_locked_by",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="transactioninferencerequest",
            name="stale_recovery_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["dispatch_backend", "status"], name="transaction_dispatc_8f0adf_idx"),
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["status", "processing_started_at"], name="transaction_status_96f122_idx"),
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["local_worker_locked_at"], name="transaction_local_w_2d3ae7_idx"),
        ),
    ]
