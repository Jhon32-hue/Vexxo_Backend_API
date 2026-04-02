"""
Publicacion ligera de eventos `payments.*`.

Todavia no existe un outbox propio del bounded context de pagos. Mientras eso
se materializa, este servicio publica despues del commit con contrato estable.
"""

from __future__ import annotations

from django.db import transaction

from common.domain_events import EventContext, EventPriority, publish_domain_event


def publish_payment_event_after_commit(
    *,
    event_type: str,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
):
    event_metadata = {
        "context": EventContext.PAYMENTS.value,
        **(metadata or {}),
    }

    def _publish():
        publish_domain_event(
            event_type=event_type,
            context=EventContext.PAYMENTS,
            payload=payload,
            metadata=event_metadata,
            priority=priority,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    transaction.on_commit(_publish)
