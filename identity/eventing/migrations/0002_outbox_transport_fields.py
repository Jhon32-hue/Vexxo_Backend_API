from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("identity_eventing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="identitydomaineventoutbox",
            name="priority",
            field=models.PositiveSmallIntegerField(default=20),
        ),
        migrations.AddField(
            model_name="identitydomaineventoutbox",
            name="correlation_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="identitydomaineventoutbox",
            name="causation_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddIndex(
            model_name="identitydomaineventoutbox",
            index=models.Index(fields=["correlation_id"], name="identity_ou_correla_860a9b_idx"),
        ),
    ]
