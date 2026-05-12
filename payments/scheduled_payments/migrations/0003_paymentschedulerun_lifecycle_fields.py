from django.db import migrations, models


def migrate_run_statuses(apps, schema_editor):
    PaymentScheduleRun = apps.get_model("scheduled_payments", "PaymentScheduleRun")
    PaymentScheduleRun.objects.filter(status="requested").update(status="scheduled")
    PaymentScheduleRun.objects.filter(status="succeeded").update(status="paid")
    PaymentScheduleRun.objects.filter(status="cancelled").update(status="canceled")


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0010_budget_attribution_fields"),
        ("scheduled_payments", "0002_paymenttemplate_budget_attribution_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentschedulerun",
            name="due_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="expected_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=20, null=True),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="expected_currency",
            field=models.CharField(default="COP", max_length=12),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="last_reminded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="materialized_transaction",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="payment_schedule_runs", to="transactions.transaction"),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="paid_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="postponed_until",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="reminder_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="reminder_stage",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="resolution_action",
            field=models.CharField(blank=True, choices=[("mark_paid", "Mark paid"), ("paid_outside_vexxo", "Paid outside Vexxo"), ("postpone", "Postpone"), ("skip", "Skip"), ("cancel", "Cancel"), ("pay_with_vexxo", "Pay with Vexxo")], default="", max_length=32),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="resolution_note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="paymentschedulerun",
            name="resolved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="paymenttemplate",
            name="cadence",
            field=models.CharField(choices=[("once", "Once"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly"), ("bimonthly", "Bimonthly"), ("quarterly", "Quarterly"), ("yearly", "Yearly")], default="monthly", max_length=24),
        ),
        migrations.AlterField(
            model_name="paymentschedulerun",
            name="status",
            field=models.CharField(choices=[("scheduled", "Scheduled"), ("due", "Due"), ("overdue", "Overdue"), ("processing", "Processing"), ("paid", "Paid"), ("paid_outside_vexxo", "Paid outside Vexxo"), ("postponed", "Postponed"), ("skipped", "Skipped"), ("canceled", "Canceled"), ("failed", "Failed")], default="scheduled", max_length=24),
        ),
        migrations.AddIndex(
            model_name="paymentschedulerun",
            index=models.Index(fields=["owner", "status", "due_on"], name="scheduled_p_owner_i_f7e8ca_idx"),
        ),
        migrations.RunPython(migrate_run_statuses, migrations.RunPython.noop),
    ]
