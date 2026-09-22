from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import security.validators
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("integration_credentials", "0001_initial"),
        ("users", "0002_userauthchallenge"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserMfaMethod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("method", models.CharField(choices=[("totp", "Authenticator app")], default="totp", max_length=16)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("active", "Active"), ("disabled", "Disabled")], db_index=True, default="pending", max_length=16)),
                ("recovery_code_hashes", models.JSONField(blank=True, default=list, validators=[security.validators.validate_safe_metadata])),
                ("last_totp_counter", models.BigIntegerField(blank=True, null=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("disabled_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("secret_credential", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="mfa_method", to="integration_credentials.integrationcredential")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mfa_methods", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="usermfamethod",
            constraint=models.UniqueConstraint(condition=models.Q(("status__in", ["pending", "active"])), fields=("user", "method"), name="uniq_active_user_mfa_method"),
        ),
    ]
