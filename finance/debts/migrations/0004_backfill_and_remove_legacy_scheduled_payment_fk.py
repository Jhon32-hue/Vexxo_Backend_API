from django.db import migrations


def backfill_payment_template_from_legacy(apps, schema_editor):
    DebtInstallment = apps.get_model("debts", "DebtInstallment")
    PaymentTemplate = apps.get_model("scheduled_payments", "PaymentTemplate")

    queryset = DebtInstallment.objects.exclude(scheduled_payment_id__isnull=True).filter(payment_template_id__isnull=True)
    for installment in queryset.iterator():
        payment_template = PaymentTemplate.objects.filter(legacy_scheduled_payment_id=installment.scheduled_payment_id).first()
        if payment_template is None:
            continue
        installment.payment_template_id = payment_template.pk
        installment.save(update_fields=["payment_template", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0012_rename_transactio_owner_i_904c0c_idx_transaction_owner_i_c2b1bd_idx_and_more"),
        ("scheduled_payments", "0005_paymenttemplate_debt_installment_and_legacy_backfill"),
        ("debts", "0003_debtinstallment_payment_template_backfill"),
    ]

    operations = [
        migrations.RunPython(backfill_payment_template_from_legacy, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="debtinstallment",
            name="scheduled_payment",
        ),
    ]
