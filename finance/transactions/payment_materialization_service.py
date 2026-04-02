"""
Materializacion contable de pagos externos.

`payments.payment_intents` modela la intencion/ejecucion externa.
Este modulo crea el reflejo final en ledger cuando el proveedor confirma el
resultado.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from finance.transactions.Models.transacciones import Transaction


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
    return tx
