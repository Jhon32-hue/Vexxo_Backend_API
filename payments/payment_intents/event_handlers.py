"""
Listeners locales de `payments`.

Mantienen la capa de UX operativa separada del outbox fuerte: señales realtime
para UI/polling y futuros gateways WebSocket, sin contaminar el dominio.
"""

from __future__ import annotations

from common.domain_events import EventContext, EventPriority, EventNames, VexxoAppDomainEvent, subscribe

from payments.payment_intents.realtime_services import publish_payment_intent_signal, publish_payout_signal


def _payment_event_extra(event: VexxoAppDomainEvent) -> dict:
    payload = event.payload or {}
    return {
        "domain_event_type": event.type,
        "correlation_id": event.correlation_id,
        "status": payload.get("status"),
        "provider": payload.get("provider"),
        "rail": payload.get("rail"),
        "amount": payload.get("amount"),
    }


def _publish_payment_signal(event: VexxoAppDomainEvent, *, signal_event: str) -> None:
    payload = event.payload or {}
    owner_id = payload.get("owner_id")
    payment_intent_id = payload.get("payment_intent_id")
    if not owner_id or not payment_intent_id:
        return
    publish_payment_intent_signal(
        owner_id=int(owner_id),
        payment_intent_id=payment_intent_id,
        event=signal_event,
        extra=_payment_event_extra(event),
    )


def _publish_payout_signal(event: VexxoAppDomainEvent, *, signal_event: str) -> None:
    payload = event.payload or {}
    owner_id = payload.get("owner_id")
    batch_id = payload.get("batch_id")
    if not owner_id or not batch_id:
        return
    publish_payout_signal(
        owner_id=int(owner_id),
        batch_id=batch_id,
        event=signal_event,
        extra={
            "domain_event_type": event.type,
            "correlation_id": event.correlation_id,
            "provider": payload.get("provider"),
            "rail": payload.get("rail"),
            "amount": payload.get("amount"),
            "currency": payload.get("currency"),
        },
    )


@subscribe(
    EventNames.PAYMENT_INTENT_CREATED,
    name="payments.publish_intent_created_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.NORMAL,
)
def handle_payment_intent_created(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.created")


@subscribe(
    EventNames.PAYMENT_INTENT_DISPATCHED,
    name="payments.publish_intent_dispatched_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.NORMAL,
)
def handle_payment_intent_dispatched(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.dispatched")


@subscribe(
    EventNames.PAYMENT_INTENT_REQUIRES_ACTION,
    name="payments.publish_intent_requires_action_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_intent_requires_action(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.requires_action")


@subscribe(
    EventNames.PAYMENT_INTENT_PROCESSING,
    name="payments.publish_intent_processing_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.NORMAL,
)
def handle_payment_intent_processing(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.processing")


@subscribe(
    EventNames.PAYMENT_INTENT_SUCCEEDED,
    name="payments.publish_intent_succeeded_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_intent_succeeded(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.succeeded")


@subscribe(
    EventNames.PAYMENT_INTENT_FAILED,
    name="payments.publish_intent_failed_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_intent_failed(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.failed")


@subscribe(
    EventNames.PAYMENT_INTENT_CANCELLED,
    name="payments.publish_intent_cancelled_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.NORMAL,
)
def handle_payment_intent_cancelled(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.cancelled")


@subscribe(
    EventNames.PAYMENT_INTENT_SETTLED,
    name="payments.publish_intent_settled_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_intent_settled(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.settled")


@subscribe(
    EventNames.PAYMENT_INTENT_REVERSED,
    name="payments.publish_intent_reversed_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_intent_reversed(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.reversed")


@subscribe(
    EventNames.PAYMENT_INTENT_DISPUTED,
    name="payments.publish_intent_disputed_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_intent_disputed(event: VexxoAppDomainEvent) -> None:
    _publish_payment_signal(event, signal_event="payment.intent.disputed")


@subscribe(
    EventNames.PAYMENT_PAYOUT_REQUESTED,
    name="payments.publish_payout_requested_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.NORMAL,
)
def handle_payment_payout_requested(event: VexxoAppDomainEvent) -> None:
    _publish_payout_signal(event, signal_event="payment.payout.requested")


@subscribe(
    EventNames.PAYMENT_PAYOUT_SUCCEEDED,
    name="payments.publish_payout_succeeded_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_payout_succeeded(event: VexxoAppDomainEvent) -> None:
    _publish_payout_signal(event, signal_event="payment.payout.succeeded")


@subscribe(
    EventNames.PAYMENT_PAYOUT_FAILED,
    name="payments.publish_payout_failed_realtime_signal",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_payout_failed(event: VexxoAppDomainEvent) -> None:
    _publish_payout_signal(event, signal_event="payment.payout.failed")
