from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("permissions", "0003_permission_scope_source_kind_constraint"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userpermissiongrant",
            name="status",
            field=models.CharField(
                choices=[
                    ("granted", "Granted"),
                    ("denied", "Denied"),
                    ("revoked", "Revoked"),
                    ("expired", "Expired"),
                ],
                default="granted",
                max_length=16,
            ),
        ),
    ]
