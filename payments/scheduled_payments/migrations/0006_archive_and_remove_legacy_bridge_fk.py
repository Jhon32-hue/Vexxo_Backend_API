from django.db import migrations


def archive_legacy_bridge_reference(apps, schema_editor):
    PaymentTemplate = apps.get_model("scheduled_payments", "PaymentTemplate")

    for template in PaymentTemplate.objects.exclude(legacy_scheduled_payment_id__isnull=True).iterator():
        execution_defaults = dict(template.execution_defaults or {})
        legacy_id = str(template.legacy_scheduled_payment_id)
        if (
            execution_defaults.get("legacy_source") == "transactions.ScheduledPayment"
            and str(execution_defaults.get("legacy_scheduled_payment_id") or "") == legacy_id
        ):
            continue
        execution_defaults["legacy_source"] = "transactions.ScheduledPayment"
        execution_defaults["legacy_scheduled_payment_id"] = legacy_id
        template.execution_defaults = execution_defaults
        template.save(update_fields=["execution_defaults", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0012_rename_transactio_owner_i_904c0c_idx_transaction_owner_i_c2b1bd_idx_and_more"),
        ("debts", "0004_backfill_and_remove_legacy_scheduled_payment_fk"),
        ("scheduled_payments", "0005_paymenttemplate_debt_installment_and_legacy_backfill"),
    ]

    operations = [
        migrations.RunPython(archive_legacy_bridge_reference, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="paymenttemplate",
            name="legacy_scheduled_payment",
        ),
    ]
