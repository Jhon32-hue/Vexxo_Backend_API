from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("identity_permissions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpermissiongrant",
            name="grant_kind",
            field=models.CharField(
                choices=[
                    ("manual", "Manual"),
                    ("entitlement", "Entitlement"),
                    ("override", "Override"),
                ],
                default="manual",
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name="userpermissiongrant",
            index=models.Index(fields=["user", "grant_kind", "status"], name="identity_pe_user_id_42deab_idx"),
        ),
    ]
