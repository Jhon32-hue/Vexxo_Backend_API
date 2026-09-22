import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0013_accountintelligencedispatchstate_dispatch_attempt_count_and_more"),
        ("consents", "0002_rename_consents_us_user_id_822cc2_idx_consents_us_user_id_973183_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpenBankingConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("provider", models.CharField(db_index=True, max_length=64)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=160)),
                ("institution_name", models.CharField(blank=True, default="", max_length=120)),
                ("country", models.CharField(blank=True, default="", max_length=2)),
                ("status", models.CharField(choices=[("pending_authorization", "Pending authorization"), ("connected", "Connected"), ("syncing", "Syncing"), ("attention_required", "Attention required"), ("revoked", "Revoked"), ("error", "Error")], db_index=True, default="pending_authorization", max_length=32)),
                ("external_connection_id", models.CharField(blank=True, db_index=True, default="", max_length=160)),
                ("scopes", models.JSONField(blank=True, default=list)),
                ("safe_metadata", models.JSONField(blank=True, default=dict)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("next_sync_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("error_message", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("consent", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="open_banking_connections", to="consents.userconsent")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="open_banking_connections", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="OpenBankingWebhookReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(db_index=True, max_length=64)),
                ("provider_event_id", models.CharField(max_length=160)),
                ("event_type", models.CharField(blank=True, default="", max_length=96)),
                ("status", models.CharField(choices=[("received", "Received"), ("processed", "Processed"), ("rejected", "Rejected"), ("failed", "Failed")], db_index=True, default="received", max_length=16)),
                ("payload_sha256", models.CharField(max_length=64)),
                ("signature_verified", models.BooleanField(default=False)),
                ("connection_reference", models.CharField(blank=True, db_index=True, default="", max_length=160)),
                ("safe_metadata", models.JSONField(blank=True, default=dict)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-received_at"]},
        ),
        migrations.CreateModel(
            name="OpenBankingAccountLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_account_id", models.CharField(max_length=160)),
                ("external_mask", models.CharField(blank=True, default="", max_length=16)),
                ("external_type", models.CharField(blank=True, default="", max_length=64)),
                ("sync_cursor", models.CharField(blank=True, default="", max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="open_banking_link", to="accounts.account")),
                ("connection", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="account_links", to="open_banking.openbankingconnection")),
            ],
            options={"ordering": ["connection_id", "account_id"]},
        ),
        migrations.AddIndex(model_name="openbankingconnection", index=models.Index(fields=["owner", "status"], name="open_bankin_owner_i_b37e2c_idx")),
        migrations.AddIndex(model_name="openbankingconnection", index=models.Index(fields=["provider", "external_connection_id"], name="open_bankin_provide_027264_idx")),
        migrations.AddConstraint(model_name="openbankingconnection", constraint=models.UniqueConstraint(condition=models.Q(("idempotency_key", ""), _negated=True), fields=("owner", "idempotency_key"), name="uniq_open_banking_owner_idempotency")),
        migrations.AddIndex(model_name="openbankingwebhookreceipt", index=models.Index(fields=["provider", "status"], name="open_bankin_provide_64be45_idx")),
        migrations.AddIndex(model_name="openbankingwebhookreceipt", index=models.Index(fields=["connection_reference"], name="open_bankin_connect_fc0744_idx")),
        migrations.AddConstraint(model_name="openbankingwebhookreceipt", constraint=models.UniqueConstraint(fields=("provider", "provider_event_id"), name="uniq_open_banking_provider_event")),
        migrations.AddConstraint(model_name="openbankingaccountlink", constraint=models.UniqueConstraint(fields=("connection", "external_account_id"), name="uniq_open_banking_external_account")),
    ]
