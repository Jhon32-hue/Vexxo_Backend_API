from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserSocialIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("google", "Google"), ("facebook", "Facebook")], max_length=32)),
                ("provider_user_id", models.CharField(max_length=128)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("email_verified", models.BooleanField(default=False)),
                ("full_name", models.CharField(blank=True, default="", max_length=255)),
                ("avatar_url", models.URLField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("linked_at", models.DateTimeField()),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                ("unlinked_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="social_identities", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["provider", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="usersocialidentity",
            constraint=models.UniqueConstraint(fields=("provider", "provider_user_id"), name="unique_social_provider_identity"),
        ),
        migrations.AddIndex(
            model_name="usersocialidentity",
            index=models.Index(fields=["user", "provider"], name="social_iden_user_id_49b9d0_idx"),
        ),
        migrations.AddIndex(
            model_name="usersocialidentity",
            index=models.Index(fields=["provider", "email"], name="social_iden_provide_b73c58_idx"),
        ),
    ]
