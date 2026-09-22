from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("READ", "Read"),
                    ("CREATE", "Create"),
                    ("UPDATE", "Update"),
                    ("DELETE", "Delete"),
                    ("AUTO_TRIGGER", "Auto Trigger"),
                    ("CALCULATE", "Calculate"),
                    ("RECOMMEND", "Recommend"),
                ],
                max_length=20,
            ),
        ),
    ]
