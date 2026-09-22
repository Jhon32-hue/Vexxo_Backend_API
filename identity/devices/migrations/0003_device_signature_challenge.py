from django.db import migrations, models
import django.db.models.deletion
import security.validators
import uuid


class Migration(migrations.Migration):
    dependencies = [("devices", "0002_rename_devices_use_is_acti_fecf96_idx_devices_use_user_id_0cc980_idx_and_more")]

    operations = [
        migrations.AddField(model_name="userdevice", name="attestation_provider", field=models.CharField(blank=True, default="", max_length=32)),
        migrations.AddField(model_name="userdevice", name="attestation_status", field=models.CharField(choices=[("unavailable", "Unavailable"), ("pending", "Pending"), ("key_verified", "Key verified"), ("platform_verified", "Platform verified"), ("rejected", "Rejected")], db_index=True, default="unavailable", max_length=24)),
        migrations.AddField(model_name="userdevice", name="key_verified_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="userdevice", name="signing_algorithm", field=models.CharField(blank=True, default="", max_length=16)),
        migrations.AddField(model_name="userdevice", name="signing_public_key", field=models.TextField(blank=True, default="")),
        migrations.AlterField(model_name="userdevice", name="metadata", field=models.JSONField(blank=True, default=dict, validators=[security.validators.validate_safe_metadata])),
        migrations.CreateModel(
            name="DeviceSignatureChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("purpose", models.CharField(choices=[("register_key", "Register device key"), ("step_up", "Step-up authentication")], default="register_key", max_length=24)),
                ("nonce_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="signature_challenges", to="devices.userdevice")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="devicesignaturechallenge", index=models.Index(fields=["device", "purpose", "expires_at"], name="devices_dev_device__5aeaee_idx")),
    ]
