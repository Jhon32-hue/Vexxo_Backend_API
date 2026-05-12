from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0013_archive_and_remove_transaction_scheduled_payment_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="scheduledpayment",
            name="tags",
        ),
        migrations.DeleteModel(
            name="ScheduledPayment",
        ),
    ]
