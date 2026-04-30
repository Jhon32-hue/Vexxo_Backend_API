from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAuthChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purpose", models.CharField(choices=[("password_recovery", "Password recovery"), ("email_verification", "Email verification"), ("magic_link", "Magic link"), ("step_up", "Step up")], max_length=32)),
                ("channel", models.CharField(choices=[("sms_code", "SMS code"), ("email_link", "Email link"), ("email_code", "Email code")], max_length=24)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("consumed", "Consumed"), ("blocked", "Blocked"), ("expired", "Expired"), ("superseded", "Superseded"), ("failed_dispatch", "Failed dispatch")], default="pending", max_length=24)),
                ("code_hash", models.CharField(blank=True, default="", max_length=64)),
                ("delivery_target_masked", models.CharField(blank=True, default="", max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("requested_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="auth_challenges", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="userauthchallenge",
            index=models.Index(fields=["user", "purpose", "status"], name="users_usera_user_id_b2d082_idx"),
        ),
        migrations.AddIndex(
            model_name="userauthchallenge",
            index=models.Index(fields=["purpose", "status", "expires_at"], name="users_usera_purpose_9af3c2_idx"),
        ),
    ]
