import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("social_identities", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialAuthHandoff",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=128, unique=True)),
                ("provider", models.CharField(choices=[("google", "Google"), ("facebook", "Facebook")], max_length=32)),
                ("login_mode", models.CharField(blank=True, default="", max_length=32)),
                ("created_user", models.BooleanField(default=False)),
                ("linked_identity", models.BooleanField(default=False)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("identity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="handoffs", to="social_identities.usersocialidentity")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="social_auth_handoffs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="socialauthhandoff",
            index=models.Index(fields=["provider", "expires_at"], name="social_iden_provide_2fc5fb_idx"),
        ),
        migrations.AddIndex(
            model_name="socialauthhandoff",
            index=models.Index(fields=["user", "provider"], name="social_iden_user_id_ae8569_idx"),
        ),
    ]
