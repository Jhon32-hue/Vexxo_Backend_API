"""
Materializacion contable de pagos externos.

`payments.payment_intents` modela la intencion/ejecucion externa.
Este modulo crea el reflejo final en ledger cuando el proveedor confirma el
resultado.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from finance.budgets.attribution import BudgetAttributionSource, BudgetScope
from finance.transactions.Models.transacciones import Transaction


def _resolve_payment_intent_schedule_run(payment_intent):
    return payment_intent.schedule_runs.select_related("template").order_by("-id").first()


def _resolve_payment_intent_budget_attribution(payment_intent) -> dict:
    latest_run = _resolve_payment_intent_schedule_run(payment_intent)
    if latest_run and latest_run.template_id:
        template = latest_run.template
        return {
            "budget_scope": getattr(template, "budget_scope", "") or BudgetScope.PERSONAL,
            "shared_budget_id": getattr(template, "shared_budget_id", None),
            "budget_attribution_source": BudgetAttributionSource.INHERITED_FROM_TEMPLATE,
        }
    return {
        "budget_scope": BudgetScope.PERSONAL if payment_intent.category_id else BudgetScope.NONE,
        "shared_budget_id": None,
        "budget_attribution_source": "",
    }


@transaction.atomic
def materialize_transaction_from_payment_intent(payment_intent):
    """
    Crea o reutiliza la transaccion contable asociada a un `PaymentIntent`.

    El detalle rico del rail vive en `payments.payment_intents`.
    Aqui solo queda el reflejo financiero para balances, reportes y ledger.
    """
    if getattr(payment_intent, "ledger_transaction", None):
        return payment_intent.ledger_transaction

    if payment_intent.account_id is None:
        return None

    latest_run = _resolve_payment_intent_schedule_run(payment_intent)
    attribution = _resolve_payment_intent_budget_attribution(payment_intent)

    tx, _created = Transaction.objects.get_or_create(
        payment_intent=payment_intent,
        defaults={
            "owner": payment_intent.owner,
            "type": Transaction.Type.EXPENSE,
            "status": Transaction.Status.POSTED,
            "amount": payment_intent.amount,
            "date": timezone.now().date(),
            "account_id": payment_intent.account_id,
            "category_id": payment_intent.category_id,
            "debt_id": getattr(getattr(latest_run, "template", None), "debt_id", None),
            "installment_id": getattr(getattr(latest_run, "template", None), "installment_id", None),
            "budget_scope": attribution["budget_scope"],
            "shared_budget_id": attribution["shared_budget_id"],
            "budget_attribution_source": attribution["budget_attribution_source"],
            "payment_schedule_run": latest_run,
            "vendor_id": payment_intent.vendor_id,
            "source": "payment_intent",
            "provider": payment_intent.provider,
            "external_id": payment_intent.provider_reference or payment_intent.provider_intent_id,
            "raw_payload": {
                "payment_intent_id": payment_intent.pk,
                "payment_type": payment_intent.payment_type,
                "rail": payment_intent.rail,
                "external_reference": payment_intent.external_reference,
                "invoice_reference": payment_intent.invoice_reference,
                "beneficiary_name": payment_intent.beneficiary_name,
                "beneficiary_account_ref": payment_intent.beneficiary_account_ref,
                "provider_reference": payment_intent.provider_reference,
                "provider_cus": payment_intent.provider_cus,
                "pricing_snapshot": payment_intent.pricing_snapshot or {},
                "fee_breakdown": payment_intent.fee_breakdown or {},
                "tax_breakdown": payment_intent.tax_breakdown or {},
            },
            "notes": f"Pago externo {payment_intent.payment_type} via {payment_intent.provider}",
            "confirmed": True,
        },
    )
    if latest_run and tx.payment_schedule_run_id != latest_run.pk:
        tx.payment_schedule_run = latest_run
        update_fields = ["payment_schedule_run"]
        template = getattr(latest_run, "template", None)
        if template and tx.debt_id != getattr(template, "debt_id", None):
            tx.debt_id = getattr(template, "debt_id", None)
            update_fields.append("debt")
        if template and tx.installment_id != getattr(template, "installment_id", None):
            tx.installment_id = getattr(template, "installment_id", None)
            update_fields.append("installment")
        tx.save(update_fields=update_fields + ["updated_at"])
    if latest_run and latest_run.materialized_transaction_id != tx.pk:
        latest_run.materialized_transaction = tx
        latest_run.save(update_fields=["materialized_transaction", "updated_at"])
    return tx
