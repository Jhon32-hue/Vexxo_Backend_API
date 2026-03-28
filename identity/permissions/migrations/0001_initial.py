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
            name="UserPermissionGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("permission_code", models.CharField(max_length=128)),
                ("scope_type", models.CharField(blank=True, default="global", max_length=64)),
                ("scope_id", models.CharField(blank=True, default="", max_length=128)),
                ("status", models.CharField(choices=[("granted", "Granted"), ("revoked", "Revoked"), ("expired", "Expired")], default="granted", max_length=16)),
                ("source", models.CharField(choices=[("system", "System"), ("plan", "Plan"), ("admin", "Admin"), ("consent", "Consent"), ("support", "Support")], default="system", max_length=16)),
                ("granted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("granted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="granted_identity_permissions", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="identity_permission_grants", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["permission_code", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="userpermissiongrant",
            constraint=models.UniqueConstraint(fields=("user", "permission_code", "scope_type", "scope_id"), name="unique_identity_permission_grant"),
        ),
        migrations.AddIndex(
            model_name="userpermissiongrant",
            index=models.Index(fields=["user", "status"], name="identity_pe_user_id_7be630_idx"),
        ),
        migrations.AddIndex(
            model_name="userpermissiongrant",
            index=models.Index(fields=["permission_code", "status"], name="identity_pe_permiss_a9c060_idx"),
        ),
    ]
