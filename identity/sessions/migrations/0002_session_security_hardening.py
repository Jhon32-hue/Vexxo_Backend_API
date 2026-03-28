from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sessions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersession",
            name="family_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="usersession",
            name="previous_refresh_jti",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="usersession",
            name="risk_level",
            field=models.CharField(
                choices=[
                    ("low", "Low"),
                    ("medium", "Medium"),
                    ("high", "High"),
                    ("critical", "Critical"),
                ],
                default="low",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="usersession",
            name="requires_step_up",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usersession",
            name="last_refreshed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="usersession",
            name="refresh_rotated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="usersession",
            index=models.Index(fields=["user", "family_id"], name="identity_se_user_id_582ece_idx"),
        ),
        migrations.AddIndex(
            model_name="usersession",
            index=models.Index(fields=["previous_refresh_jti"], name="identity_se_previou_861dd5_idx"),
        ),
    ]
