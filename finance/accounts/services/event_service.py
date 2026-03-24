from __future__ import annotations

import logging

from django.db import transaction

from common.domain_events import EventContext, EventPriority, publish_domain_event

from finance.accounts.models.outbox import DomainEventOutbox

logger = logging.getLogger(__name__)


def enqueue_domain_event(
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    idempotency_key: str,
    payload: dict,
    metadata: dict | None = None,
) -> DomainEventOutbox:
    """
    Registra evento en outbox dentro de la transaccion actual.
    """
    event, _created = DomainEventOutbox.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "event_type": event_type,
            "payload": payload,
            "metadata": metadata or {},
        },
    )
    return event


def publish_outbox_event(event: DomainEventOutbox) -> None:
    """
    Publica un evento de outbox en el event bus local.
    Preparado para reemplazar por Kafka/SNS sin tocar use cases.
    """
    if event.published_at:
        return

    try:
        context_value = (event.metadata or {}).get("context", EventContext.SYSTEM.value)
        context = EventContext(context_value)
    except Exception:
        context = EventContext.SYSTEM

    try:
        publish_domain_event(
            event_type=event.event_type,
            context=context,
            payload=event.payload,
            metadata=event.metadata or {},
            priority=EventPriority.NORMAL,
            correlation_id=(event.metadata or {}).get("correlation_id"),
            causation_id=(event.metadata or {}).get("causation_id"),
        )
        event.mark_published()
    except Exception as exc:
        logger.exception("[accounts] Error publicando outbox id=%s", event.pk)
        event.mark_failed(str(exc))


def publish_after_commit(event: DomainEventOutbox) -> None:
    transaction.on_commit(lambda: publish_outbox_event(event))
