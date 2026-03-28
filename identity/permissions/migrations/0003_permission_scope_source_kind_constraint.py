from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("permissions", "0002_permission_grant_kind"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="userpermissiongrant",
            name="unique_identity_permission_grant",
        ),
        migrations.AddConstraint(
            model_name="userpermissiongrant",
            constraint=models.UniqueConstraint(
                fields=("user", "permission_code", "scope_type", "scope_id", "source", "grant_kind"),
                name="unique_identity_permission_scope_source_kind",
            ),
        ),
    ]
