from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("devices", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(max_length=128, unique=True)),
                ("refresh_jti", models.CharField(blank=True, default="", max_length=128)),
                ("access_jti", models.CharField(blank=True, default="", max_length=128)),
                ("session_type", models.CharField(choices=[("password", "Password"), ("social", "Social OAuth"), ("api", "API"), ("internal", "Internal")], default="password", max_length=16)),
                ("status", models.CharField(choices=[("active", "Active"), ("revoked", "Revoked"), ("expired", "Expired"), ("failed", "Failed")], default="active", max_length=16)),
                ("provider", models.CharField(blank=True, default="", max_length=32)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("authenticated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revocation_reason", models.CharField(blank=True, default="", max_length=64)),
                ("correlation_id", models.CharField(blank=True, default="", max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("device", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sessions", to="devices.userdevice")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="identity_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-authenticated_at", "-created_at"]},
        ),
        migrations.AddIndex(
            model_name="usersession",
            index=models.Index(fields=["user", "status"], name="identity_se_user_id_7ca772_idx"),
        ),
        migrations.AddIndex(
            model_name="usersession",
            index=models.Index(fields=["session_key"], name="identity_se_session_d0e623_idx"),
        ),
        migrations.AddIndex(
            model_name="usersession",
            index=models.Index(fields=["refresh_jti"], name="identity_se_refresh_0d5209_idx"),
        ),
    ]
