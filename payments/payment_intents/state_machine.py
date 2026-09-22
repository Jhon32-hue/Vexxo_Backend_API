from __future__ import annotations

from payments.payment_intents.models import PaymentIntent


ALLOWED_PROVIDER_TRANSITIONS = {
    PaymentIntent.Status.CREATED: {
        PaymentIntent.Status.DISPATCHED,
        PaymentIntent.Status.PROCESSING,
        PaymentIntent.Status.REQUIRES_ACTION,
        PaymentIntent.Status.SUCCEEDED,
        PaymentIntent.Status.FAILED,
        PaymentIntent.Status.CANCELLED,
    },
    PaymentIntent.Status.DISPATCHED: {
        PaymentIntent.Status.PROCESSING,
        PaymentIntent.Status.REQUIRES_ACTION,
        PaymentIntent.Status.SUCCEEDED,
        PaymentIntent.Status.FAILED,
        PaymentIntent.Status.CANCELLED,
    },
    PaymentIntent.Status.PROCESSING: {
        PaymentIntent.Status.REQUIRES_ACTION,
        PaymentIntent.Status.SUCCEEDED,
        PaymentIntent.Status.FAILED,
        PaymentIntent.Status.CANCELLED,
    },
    PaymentIntent.Status.REQUIRES_ACTION: {
        PaymentIntent.Status.PROCESSING,
        PaymentIntent.Status.SUCCEEDED,
        PaymentIntent.Status.FAILED,
        PaymentIntent.Status.CANCELLED,
    },
    PaymentIntent.Status.SUCCEEDED: {
        PaymentIntent.Status.SETTLED,
        PaymentIntent.Status.REVERSED,
        PaymentIntent.Status.DISPUTED,
    },
    PaymentIntent.Status.SETTLED: {
        PaymentIntent.Status.REVERSED,
        PaymentIntent.Status.DISPUTED,
    },
    PaymentIntent.Status.FAILED: set(),
    PaymentIntent.Status.CANCELLED: set(),
    PaymentIntent.Status.REVERSED: {PaymentIntent.Status.DISPUTED},
    PaymentIntent.Status.DISPUTED: set(),
}


def can_apply_provider_transition(current: str, target: str) -> bool:
    current = str(current or "").strip().lower()
    target = str(target or "").strip().lower()
    return not target or current == target or target in ALLOWED_PROVIDER_TRANSITIONS.get(current, set())
