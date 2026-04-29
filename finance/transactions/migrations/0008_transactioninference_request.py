from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_alter_account_shared_from_user_and_more"),
        ("transactions", "0007_add_voice_transaction_channel"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TransactionInferenceRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source", models.CharField(choices=[("voice", "voz")], db_index=True, default="voice", max_length=32)),
                ("provider", models.CharField(db_index=True, default="voice_ai", max_length=64)),
                ("request_id", models.CharField(db_index=True, max_length=64)),
                ("idempotency_key", models.CharField(max_length=160, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "en cola"),
                            ("processing", "procesando"),
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
                ("audio_object_ref", models.CharField(max_length=512)),
                ("audio_content_type", models.CharField(blank=True, default="", max_length=128)),
                ("audio_duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("language", models.CharField(blank=True, default="", max_length=16)),
                ("provider_request_id", models.CharField(blank=True, default="", max_length=128)),
                ("provider_job_id", models.CharField(blank=True, default="", max_length=128)),
                ("provider_correlation_id", models.CharField(blank=True, default="", max_length=128)),
                ("transcript", models.TextField(blank=True, default="")),
                ("transcript_confidence", models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ("parser_version", models.CharField(blank=True, default="", max_length=64)),
                ("result_summary", models.JSONField(blank=True, default=dict)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("normalized_payload", models.JSONField(blank=True, default=dict)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("processing_started_at", models.DateTimeField(blank=True, null=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transaction_inference_requests",
                        to="accounts.account",
                    ),
                ),
                (
                    "intake_batch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inference_requests",
                        to="transactions.transactionintakebatch",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transaction_inference_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requested_transaction_inferences",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-requested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["owner", "status"], name="transaction_owner_i_fcd55e_idx"),
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["requested_by", "requested_at"], name="transaction_request_487988_idx"),
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["status", "next_attempt_at"], name="transaction_status_2a51fa_idx"),
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["request_id"], name="transaction_request_bb6d97_idx"),
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["provider", "provider_request_id"], name="transaction_provide_1c43ef_idx"),
        ),
        migrations.AddIndex(
            model_name="transactioninferencerequest",
            index=models.Index(fields=["account", "requested_at"], name="transaction_account_d2a937_idx"),
        ),
        migrations.AddConstraint(
            model_name="transactioninferencerequest",
            constraint=models.CheckConstraint(
                check=models.Q(("retry_count__gte", 0)),
                name="transaction_inference_retry_count_non_negative",
            ),
        ),
    ]
