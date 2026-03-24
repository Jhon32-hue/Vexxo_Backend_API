from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_balancesnapshot_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountmembership",
            name="accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
