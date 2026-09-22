from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("devices", "0004_platform_attestation")]

    operations = [
        migrations.AddField(
            model_name="userdevice",
            name="platform_verification_expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="userdevice",
            name="attestation_failure_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="userdevice",
            name="last_attestation_failure_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
