"""
Outbox y publicacion confiable de eventos `payments.*`.

`payments` ya no publica directo desde el request path. El request deja el
evento en outbox y un worker operativo lo publica despues.
"""

from __future__ import annotations

import hashlib
import json
import logging

from django.conf import settings
from django.db import transaction

from common.domain_events import EventContext, EventPriority, publish_domain_event
from payments.payment_intents.models import PaymentDomainEventOutbox

logger = logging.getLogger(__name__)


def _local_autopublish_enabled() -> bool:
    return bool(getattr(settings, "DOMAIN_EVENTS_LOCAL_AUTOPUBLISH_ENABLED", False))


def stable_payment_event_key(event_type: str, aggregate_type: str, aggregate_id: str | int, payload: dict) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{event_type}:{aggregate_type}:{aggregate_id}:{digest}"


def enqueue_payment_domain_event(
    *,
    aggregate_type: str,
    aggregate_id: str | int,
    event_type: str,
    idempotency_key: str,
    payload: dict,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    metadata: dict | None = None,
) -> PaymentDomainEventOutbox:
    event, _created = PaymentDomainEventOutbox.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "aggregate_type": str(aggregate_type or "").strip(),
            "aggregate_id": str(aggregate_id),
            "event_type": str(event_type or "").strip(),
            "correlation_id": str(correlation_id or "")[:64],
            "causation_id": str(causation_id or "")[:64],
            "request_id": str((metadata or {}).get("request_id") or "")[:64],
            "payload": payload or {},
            "metadata": metadata or {},
        },
    )
    return event


def publish_payment_outbox_event(event: PaymentDomainEventOutbox) -> None:
    if event.published_at:
        return

    try:
        context_value = (event.metadata or {}).get("context", EventContext.PAYMENTS.value)
        context = EventContext(context_value)
    except Exception:
        context = EventContext.PAYMENTS

    try:
        publish_metadata = dict(event.metadata or {})
        publish_metadata.setdefault("outbox_event_id", str(event.pk))
        publish_metadata.setdefault("projection_event_key", str(event.pk))
        publish_metadata.setdefault("outbox_idempotency_key", str(event.idempotency_key or ""))
        publish_domain_event(
            event_type=event.event_type,
            context=context,
            payload=event.payload,
            metadata=publish_metadata,
            priority=EventPriority.NORMAL,
            correlation_id=event.correlation_id or (event.metadata or {}).get("correlation_id"),
            causation_id=event.causation_id or (event.metadata or {}).get("causation_id"),
            raise_required_listener_errors=True,
        )
        event.mark_published()
    except Exception as exc:
        logger.exception("[payments] Error publicando outbox id=%s", event.pk)
        event.mark_failed(str(exc))


def publish_payment_event_after_commit(
    *,
    event_type: str,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> PaymentDomainEventOutbox:
    event_metadata = {
        "context": EventContext.PAYMENTS.value,
        "priority": int(priority),
        **(metadata or {}),
    }
    aggregate_type = str(event_metadata.get("aggregate_type") or "payment")
    aggregate_id = (
        str(event_metadata.get("aggregate_id") or "")
        or str((payload or {}).get("payment_intent_id") or "")
        or str((payload or {}).get("instruction_id") or "")
        or str((payload or {}).get("batch_id") or "")
        or str((payload or {}).get("template_id") or "")
        or str((payload or {}).get("schedule_run_id") or "")
        or str(correlation_id or "")
    )
    idempotency_key = stable_payment_event_key(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id or "payments",
        payload=payload or {},
    )
    event = enqueue_payment_domain_event(
        aggregate_type=aggregate_type or "payment",
        aggregate_id=aggregate_id or "payments",
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=payload or {},
        correlation_id=correlation_id,
        causation_id=causation_id,
        metadata=event_metadata,
    )
    if _local_autopublish_enabled() and not getattr(event, "_local_publish_scheduled", False):
        event._local_publish_scheduled = True

        def _publish_local_event() -> None:
            fresh = PaymentDomainEventOutbox.objects.filter(pk=event.pk).first()
            if fresh is None or fresh.published_at:
                return
            publish_payment_outbox_event(fresh)

        transaction.on_commit(_publish_local_event)
    return event
