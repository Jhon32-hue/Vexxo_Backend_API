from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_device_id", models.CharField(blank=True, default="", max_length=128)),
                ("fingerprint", models.CharField(max_length=255)),
                ("name", models.CharField(blank=True, default="", max_length=120)),
                ("device_type", models.CharField(choices=[("mobile", "Mobile"), ("web", "Web"), ("tablet", "Tablet"), ("desktop", "Desktop"), ("server", "Server"), ("other", "Other")], default="web", max_length=16)),
                ("platform", models.CharField(blank=True, default="", max_length=32)),
                ("os_version", models.CharField(blank=True, default="", max_length=64)),
                ("app_version", models.CharField(blank=True, default="", max_length=64)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("push_token", models.CharField(blank=True, default="", max_length=255)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("locale", models.CharField(blank=True, default="", max_length=16)),
                ("timezone_name", models.CharField(blank=True, default="", max_length=64)),
                ("trust_level", models.CharField(choices=[("unknown", "Unknown"), ("trusted", "Trusted"), ("suspicious", "Suspicious"), ("blocked", "Blocked")], default="unknown", max_length=16)),
                ("is_active", models.BooleanField(default=True)),
                ("is_primary", models.BooleanField(default=False)),
                ("first_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("trusted_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="identity_devices", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-last_seen_at", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="userdevice",
            constraint=models.UniqueConstraint(fields=("user", "fingerprint"), name="unique_user_device_fingerprint"),
        ),
        migrations.AddIndex(
            model_name="userdevice",
            index=models.Index(fields=["user", "is_active"], name="devices_use_is_acti_fecf96_idx"),
        ),
        migrations.AddIndex(
            model_name="userdevice",
            index=models.Index(fields=["user", "trust_level"], name="devices_use_trust__c1b849_idx"),
        ),
        migrations.AddIndex(
            model_name="userdevice",
            index=models.Index(fields=["external_device_id"], name="devices_ext_extern_95cb5b_idx"),
        ),
    ]
