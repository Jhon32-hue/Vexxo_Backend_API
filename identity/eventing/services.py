"""
Servicios de outbox para el bounded context identity.
"""

from __future__ import annotations

import hashlib
import json
import logging

from django.db import transaction

from common.domain_events import EventContext, EventPriority, publish_domain_event
from identity.eventing.models import IdentityDomainEventOutbox

logger = logging.getLogger(__name__)


def stable_identity_event_key(event_type: str, aggregate_type: str, aggregate_id: str | int, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{event_type}:{aggregate_type}:{aggregate_id}:{digest}"


def enqueue_identity_domain_event(
    *,
    aggregate_type: str,
    aggregate_id: str | int,
    event_type: str,
    idempotency_key: str,
    payload: dict,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    metadata: dict | None = None,
) -> IdentityDomainEventOutbox:
    event, _created = IdentityDomainEventOutbox.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "event_type": event_type,
            "priority": int(priority),
            "correlation_id": correlation_id or "",
            "causation_id": causation_id or "",
            "payload": payload,
            "metadata": metadata or {},
        },
    )
    return event


def publish_identity_outbox_event(event: IdentityDomainEventOutbox) -> None:
    if event.published_at:
        return

    try:
        context_value = (event.metadata or {}).get("context", EventContext.IDENTITY.value)
        context = EventContext(context_value)
    except Exception:
        context = EventContext.IDENTITY

    try:
        publish_domain_event(
            event_type=event.event_type,
            context=context,
            payload=event.payload,
            metadata=event.metadata or {},
            priority=EventPriority(int(event.priority or EventPriority.NORMAL)),
            correlation_id=event.correlation_id or (event.metadata or {}).get("correlation_id"),
            causation_id=event.causation_id or (event.metadata or {}).get("causation_id"),
        )
        event.mark_published()
    except Exception as exc:
        logger.exception("[identity] Error publicando outbox id=%s", event.pk)
        event.mark_failed(str(exc))


def publish_identity_after_commit(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | int,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> IdentityDomainEventOutbox:
    event_metadata = dict(metadata or {})
    if correlation_id:
        event_metadata.setdefault("correlation_id", correlation_id)
    if causation_id:
        event_metadata.setdefault("causation_id", causation_id)
    idempotency_key = stable_identity_event_key(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )
    event = enqueue_identity_domain_event(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=payload,
        priority=priority,
        correlation_id=correlation_id,
        causation_id=causation_id,
        metadata=event_metadata,
    )
    transaction.on_commit(lambda: publish_identity_outbox_event(event))
    return event
