from django.db import migrations, models


def backfill_installment_payment_template(apps, schema_editor):
    DebtInstallment = apps.get_model("debts", "DebtInstallment")
    PaymentTemplate = apps.get_model("scheduled_payments", "PaymentTemplate")

    for installment in DebtInstallment.objects.exclude(scheduled_payment_id__isnull=True).iterator():
        payment_template = PaymentTemplate.objects.filter(legacy_scheduled_payment_id=installment.scheduled_payment_id).first()
        if payment_template is None:
            continue
        installment.payment_template_id = payment_template.pk
        installment.save(update_fields=["payment_template", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("scheduled_payments", "0005_paymenttemplate_debt_installment_and_legacy_backfill"),
        ("debts", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="debtinstallment",
            name="payment_template",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="debt_installments", to="scheduled_payments.paymenttemplate"),
        ),
        migrations.RunPython(backfill_installment_payment_template, migrations.RunPython.noop),
    ]
