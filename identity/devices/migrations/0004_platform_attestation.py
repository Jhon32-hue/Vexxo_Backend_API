import django.db.models.deletion
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("devices", "0003_device_signature_challenge")]

    operations = [
        migrations.AddField(
            model_name="userdevice",
            name="attestation_counter",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="userdevice",
            name="attestation_key_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="userdevice",
            name="attestation_public_key",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="userdevice",
            name="platform_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="DevicePlatformAttestationChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("provider", models.CharField(choices=[("play_integrity", "Google Play Integrity"), ("app_attest", "Apple App Attest")], max_length=24)),
                ("nonce_hash", models.CharField(max_length=64)),
                ("request_hash", models.CharField(max_length=128)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attestation_challenges", to="devices.userdevice")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="deviceplatformattestationchallenge",
            index=models.Index(fields=["device", "provider", "expires_at"], name="devices_dev_device__179b31_idx"),
        ),
    ]
