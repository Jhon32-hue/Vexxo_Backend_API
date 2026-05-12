from django.db import migrations


def archive_legacy_scheduled_payment_reference(apps, schema_editor):
    Transaction = apps.get_model("transactions", "Transaction")

    for tx in Transaction.objects.exclude(scheduled_payment_id__isnull=True).iterator():
        raw_payload = dict(tx.raw_payload or {})
        legacy_id = str(tx.scheduled_payment_id)
        if (
            raw_payload.get("legacy_source") == "transactions.ScheduledPayment"
            and str(raw_payload.get("legacy_scheduled_payment_id") or "") == legacy_id
        ):
            continue
        raw_payload["legacy_source"] = "transactions.ScheduledPayment"
        raw_payload["legacy_scheduled_payment_id"] = legacy_id
        tx.raw_payload = raw_payload
        tx.save(update_fields=["raw_payload", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("scheduled_payments", "0006_archive_and_remove_legacy_bridge_fk"),
        ("transactions", "0012_rename_transactio_owner_i_904c0c_idx_transaction_owner_i_c2b1bd_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(archive_legacy_scheduled_payment_reference, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="transaction",
            name="scheduled_payment",
        ),
    ]
