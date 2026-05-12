import hashlib
from datetime import datetime, time

from django.db import migrations, models
from django.utils import timezone


def _aware_due_datetime(due_date):
    if due_date is None:
        return None
    naive_dt = datetime.combine(due_date, time(hour=9, minute=0))
    current_tz = timezone.get_current_timezone()
    return timezone.make_aware(naive_dt, current_tz) if timezone.is_naive(naive_dt) else naive_dt


def backfill_legacy_scheduled_payments(apps, schema_editor):
    ScheduledPayment = apps.get_model("transactions", "ScheduledPayment")
    PaymentTemplate = apps.get_model("scheduled_payments", "PaymentTemplate")
    PaymentScheduleRun = apps.get_model("scheduled_payments", "PaymentScheduleRun")

    for scheduled_payment in ScheduledPayment.objects.all().iterator():
        next_run_at = _aware_due_datetime(scheduled_payment.due_date)
        currency = "COP"
        if getattr(scheduled_payment, "account_id", None):
            account = getattr(scheduled_payment, "account", None)
            if account is None:
                account = scheduled_payment.account
            currency = getattr(account, "currency", "") or "COP"

        template, _created = PaymentTemplate.objects.get_or_create(
            legacy_scheduled_payment_id=scheduled_payment.pk,
            defaults={
                "owner_id": scheduled_payment.owner_id,
                "account_id": scheduled_payment.account_id,
                "category_id": scheduled_payment.category_id,
                "shared_budget_id": scheduled_payment.shared_budget_id,
                "vendor_id": scheduled_payment.vendor_id,
                "debt_id": scheduled_payment.debt_id,
                "installment_id": scheduled_payment.installment_id,
                "name": scheduled_payment.name,
                "payment_type": "bill",
                "amount_mode": "fixed",
                "default_amount": scheduled_payment.amount,
                "currency": currency,
                "cadence": "once",
                "interval_count": 1,
                "execution_defaults": {"origin": "legacy_scheduled_payment_bridge_migration"},
                "next_run_at": next_run_at,
                "is_active": scheduled_payment.status == "pending",
                "budget_scope": getattr(scheduled_payment, "budget_scope", "") or "",
                "budget_attribution_source": getattr(scheduled_payment, "budget_attribution_source", "") or "",
            },
        )

        updates = []
        desired_values = {
            "owner_id": scheduled_payment.owner_id,
            "account_id": scheduled_payment.account_id,
            "category_id": scheduled_payment.category_id,
            "shared_budget_id": scheduled_payment.shared_budget_id,
            "vendor_id": scheduled_payment.vendor_id,
            "debt_id": scheduled_payment.debt_id,
            "installment_id": scheduled_payment.installment_id,
            "name": scheduled_payment.name,
            "payment_type": "bill",
            "amount_mode": "fixed",
            "default_amount": scheduled_payment.amount,
            "currency": currency,
            "cadence": "once",
            "interval_count": 1,
            "next_run_at": next_run_at,
            "is_active": scheduled_payment.status == "pending",
            "budget_scope": getattr(scheduled_payment, "budget_scope", "") or "",
            "budget_attribution_source": getattr(scheduled_payment, "budget_attribution_source", "") or "",
        }
        for field_name, desired_value in desired_values.items():
            if getattr(template, field_name) != desired_value:
                setattr(template, field_name, desired_value)
                updates.append(field_name)
        if updates:
            template.save(update_fields=updates + ["updated_at"])

        if template.is_active and template.next_run_at and not PaymentScheduleRun.objects.filter(template_id=template.pk).exists():
            raw = f"legacy-bridge:{scheduled_payment.pk}:{template.next_run_at.isoformat()}"
            PaymentScheduleRun.objects.create(
                owner_id=template.owner_id,
                template_id=template.pk,
                scheduled_for=template.next_run_at,
                due_on=scheduled_payment.due_date,
                expected_amount=template.default_amount,
                expected_currency=template.currency,
                status="scheduled",
                idempotency_key=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                run_payload={
                    "origin": "legacy_scheduled_payment_bridge_migration",
                    "legacy_scheduled_payment_id": str(scheduled_payment.pk),
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ("debts", "0002_initial"),
        ("scheduled_payments", "0004_rename_scheduled_p_owner_i_f7e8ca_idx_scheduled_p_owner_i_ac7564_idx_and_more"),
        ("transactions", "0012_rename_transactio_owner_i_904c0c_idx_transaction_owner_i_c2b1bd_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymenttemplate",
            name="debt",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="payment_templates", to="debts.debt"),
        ),
        migrations.AddField(
            model_name="paymenttemplate",
            name="installment",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="payment_templates", to="debts.debtinstallment"),
        ),
        migrations.RunPython(backfill_legacy_scheduled_payments, migrations.RunPython.noop),
    ]
