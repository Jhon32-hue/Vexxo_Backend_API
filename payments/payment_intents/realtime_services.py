"""
Senalizacion realtime para `payments`.

No reemplaza el outbox fuerte del dominio. Lo complementa con eventos minimos
para UI, polling tecnico o futuros gateways WebSocket detras de API Gateway.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from realtime.consumers.models import RealtimeSignal


def create_payment_realtime_signal(
    *,
    owner_id: int,
    event: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any] | None = None,
) -> RealtimeSignal:
    signal = RealtimeSignal.objects.create(
        owner_id=owner_id,
        channel="payments",
        event=(event or "payment.changed")[:128],
        aggregate_type=(aggregate_type or "payment")[:64],
        aggregate_id=(aggregate_id or "")[:64],
        payload=dict(payload or {}),
    )
    transaction.on_commit(lambda: signal.mark_published())
    return signal


def publish_payment_intent_signal(*, owner_id: int, payment_intent_id: int | str, event: str, extra: dict | None = None) -> RealtimeSignal:
    return create_payment_realtime_signal(
        owner_id=owner_id,
        event=event,
        aggregate_type="payment",
        aggregate_id=str(payment_intent_id),
        payload={
            "owner_id": owner_id,
            "payment_intent_id": str(payment_intent_id),
            "event": event,
            "extra": dict(extra or {}),
        },
    )


def publish_payout_signal(*, owner_id: int, batch_id: int | str, event: str, extra: dict | None = None) -> RealtimeSignal:
    return create_payment_realtime_signal(
        owner_id=owner_id,
        event=event,
        aggregate_type="payout_batch",
        aggregate_id=str(batch_id),
        payload={
            "owner_id": owner_id,
            "batch_id": str(batch_id),
            "event": event,
            "extra": dict(extra or {}),
        },
    )
