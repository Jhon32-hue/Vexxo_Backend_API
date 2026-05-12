"""
Listeners locales de `payments.scheduled_payments`.

Sincronizan el lifecycle de `PaymentScheduleRun` con el resultado real del
`PaymentIntent` cuando el usuario paga con Vexxo.
"""

from __future__ import annotations

from common.domain_events import EventContext, EventPriority, EventNames, VexxoAppDomainEvent, subscribe

from payments.payment_intents.models import PaymentIntent
from payments.scheduled_payments.services import sync_schedule_run_from_payment_intent_status


def _sync_from_payment_event(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    payment_intent_id = payload.get("payment_intent_id")
    if not payment_intent_id:
        return
    payment_intent = PaymentIntent.objects.filter(pk=payment_intent_id).first()
    if payment_intent is None:
        return
    sync_schedule_run_from_payment_intent_status(payment_intent=payment_intent)


@subscribe(
    EventNames.PAYMENT_INTENT_SUCCEEDED,
    name="scheduled_payments.sync_run_when_payment_intent_succeeded",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
@subscribe(
    EventNames.PAYMENT_INTENT_SETTLED,
    name="scheduled_payments.sync_run_when_payment_intent_settled",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
@subscribe(
    EventNames.PAYMENT_INTENT_FAILED,
    name="scheduled_payments.sync_run_when_payment_intent_failed",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
@subscribe(
    EventNames.PAYMENT_INTENT_CANCELLED,
    name="scheduled_payments.sync_run_when_payment_intent_cancelled",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.NORMAL,
)
def handle_payment_intent_run_sync(event: VexxoAppDomainEvent) -> None:
    _sync_from_payment_event(event)
