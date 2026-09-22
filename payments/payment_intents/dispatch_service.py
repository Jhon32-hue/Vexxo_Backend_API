from __future__ import annotations

from django.db import transaction

from payments.payment_intents.adapters import get_payment_provider_adapter
from payments.payment_intents.models import PaymentIntent
from payments.payment_intents.services import (
    mark_payment_intent_dispatched,
    mark_payment_intent_failed,
    mark_payment_intent_processing,
    mark_payment_intent_requires_action,
    mark_payment_intent_succeeded,
    record_payment_provider_reference,
)


@transaction.atomic
def dispatch_payment_intent(*, payment_intent: PaymentIntent, ephemeral_payload: dict) -> PaymentIntent:
    payment_intent = PaymentIntent.objects.select_for_update().get(pk=payment_intent.pk)
    if payment_intent.status != PaymentIntent.Status.CREATED:
        return payment_intent
    result = get_payment_provider_adapter(payment_intent.provider).dispatch(
        payment_intent,
        ephemeral_payload=ephemeral_payload,
    )
    metadata = dict(result.get("metadata") or {})
    payment_intent = mark_payment_intent_dispatched(
        payment_intent,
        provider_intent_id=str(result.get("provider_intent_id") or ""),
        provider_metadata=metadata,
    )
    record_payment_provider_reference(
        payment_intent,
        provider_reference=str(result.get("provider_reference") or ""),
        provider_metadata=metadata,
    )
    provider_status = str(result.get("status") or "").lower()
    if provider_status in {"approved", "succeeded"}:
        return mark_payment_intent_succeeded(
            payment_intent,
            provider_intent_id=str(result.get("provider_intent_id") or ""),
            provider_metadata=metadata,
        )
    if provider_status in {"declined", "error", "failed"}:
        return mark_payment_intent_failed(
            payment_intent,
            failure_code=f"provider_{provider_status}"[:64],
            failure_message="El proveedor rechazo el pago.",
            provider_metadata=metadata,
        )
    if metadata.get("redirect_url"):
        return mark_payment_intent_requires_action(payment_intent, provider_metadata=metadata)
    return mark_payment_intent_processing(payment_intent, provider_metadata=metadata)
