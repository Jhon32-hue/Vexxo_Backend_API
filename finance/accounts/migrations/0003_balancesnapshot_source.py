from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_backfill_account_memberships"),
    ]

    operations = [
        migrations.AddField(
            model_name="balancesnapshot",
            name="source",
            field=models.CharField(
                blank=True,
                default="scheduled_job",
                help_text="Origen del snapshot: scheduled_job, manual_recheck, post_incident, etc.",
                max_length=32,
            ),
        ),
    ]
