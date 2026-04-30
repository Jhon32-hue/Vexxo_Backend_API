from __future__ import annotations

import hashlib
import json
import logging

from common.domain_events import EventContext, EventPriority, publish_domain_event
from finance.transactions.Models.outbox import TransactionDomainEventOutbox
from tasks.outbox_autopublish import schedule_local_outbox_autopublish

logger = logging.getLogger(__name__)


def stable_transaction_event_key(event_type: str, aggregate_type: str, aggregate_id: str | int, payload: dict) -> str:
    raw = json.dumps(
        {
            "event_type": str(event_type or ""),
            "aggregate_type": str(aggregate_type or ""),
            "aggregate_id": str(aggregate_id or ""),
            "payload": payload or {},
        },
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"txevt:{digest}"


def enqueue_transaction_domain_event(
    *,
    aggregate_type: str,
    aggregate_id: str | int,
    event_type: str,
    idempotency_key: str,
    payload: dict,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    metadata: dict | None = None,
) -> TransactionDomainEventOutbox:
    event, _created = TransactionDomainEventOutbox.objects.get_or_create(
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


def publish_transaction_outbox_event(event: TransactionDomainEventOutbox) -> None:
    if event.published_at:
        return
    try:
        context_value = (event.metadata or {}).get("context", EventContext.TRANSACTIONS.value)
        context = EventContext(context_value)
    except Exception:
        context = EventContext.TRANSACTIONS

    try:
        priority_value = (event.metadata or {}).get("priority", int(EventPriority.NORMAL))
        try:
            priority = EventPriority(int(priority_value))
        except Exception:
            priority = EventPriority.NORMAL
        publish_metadata = dict(event.metadata or {})
        publish_metadata.setdefault("outbox_event_id", str(event.pk))
        publish_metadata.setdefault("projection_event_key", str(event.pk))
        publish_metadata.setdefault("outbox_idempotency_key", str(event.idempotency_key or ""))
        publish_domain_event(
            event_type=event.event_type,
            context=context,
            payload=event.payload,
            metadata=publish_metadata,
            priority=priority,
            correlation_id=event.correlation_id or (event.metadata or {}).get("correlation_id"),
            causation_id=event.causation_id or (event.metadata or {}).get("causation_id"),
            raise_required_listener_errors=True,
        )
        event.mark_published()
    except Exception as exc:
        logger.exception("[transactions] Error publicando outbox id=%s", event.pk)
        event.mark_failed(str(exc))


def publish_transaction_event_after_commit(
    *,
    event_type: str,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> TransactionDomainEventOutbox:
    event_metadata = {
        "context": EventContext.TRANSACTIONS.value,
        "priority": int(priority),
        **(metadata or {}),
    }
    aggregate_type = str(event_metadata.get("aggregate_type") or "transaction")
    aggregate_id = (
        str(event_metadata.get("aggregate_id") or "")
        or str((payload or {}).get("transaction_id") or "")
        or str((payload or {}).get("participant_id") or "")
        or str((payload or {}).get("scheduled_payment_id") or "")
        or str(correlation_id or "")
    )
    idempotency_key = stable_transaction_event_key(
        event_type=event_type,
        aggregate_type=aggregate_type or "transaction",
        aggregate_id=aggregate_id or "transactions",
        payload=payload or {},
    )
    event = enqueue_transaction_domain_event(
        aggregate_type=aggregate_type or "transaction",
        aggregate_id=aggregate_id or "transactions",
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=payload or {},
        correlation_id=correlation_id,
        causation_id=causation_id,
        metadata=event_metadata,
    )
    schedule_local_outbox_autopublish(
        event,
        reload_event=lambda event_id: TransactionDomainEventOutbox.objects.filter(pk=event_id).first(),
        publish_event=publish_transaction_outbox_event,
    )
    return event
