"""
Senalizacion realtime para pagos programados.

Mantiene feedback liviano de UI sobre ocurrencias `PaymentScheduleRun` sin
reemplazar notificaciones durables ni el outbox fuerte de pagos.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from realtime.consumers.models import RealtimeSignal


def publish_schedule_run_signal(
    *,
    owner_id: int,
    schedule_run_id: int | str,
    event: str,
    extra: dict[str, Any] | None = None,
) -> RealtimeSignal:
    signal = RealtimeSignal.objects.create(
        owner_id=owner_id,
        channel="payments",
        event=(event or "payment.schedule_run.changed")[:128],
        aggregate_type="payment_schedule_run",
        aggregate_id=str(schedule_run_id),
        payload={
            "owner_id": owner_id,
            "schedule_run_id": str(schedule_run_id),
            "event": event,
            "extra": dict(extra or {}),
        },
    )
    transaction.on_commit(lambda: signal.mark_published())
    return signal
