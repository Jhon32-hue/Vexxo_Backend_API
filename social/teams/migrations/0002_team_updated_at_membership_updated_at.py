from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("teams", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="team",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="membership",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
