from __future__ import annotations

import hashlib
import json
import logging

from alerts.alerts.models.outbox import AlertDomainEventOutbox
from common.domain_events import EventContext, EventPriority, publish_domain_event
from tasks.outbox_autopublish import schedule_local_outbox_autopublish

logger = logging.getLogger(__name__)


def _alerts_outbox_retry_config() -> dict:
    return {
        "max_retries": max(1, int(getattr(settings, "ALERTS_OUTBOX_MAX_RETRIES", 10))),
    }


def stable_alert_event_key(event_type: str, aggregate_type: str, aggregate_id: str | int, payload: dict) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{event_type}:{aggregate_type}:{aggregate_id}:{digest}"


def enqueue_alert_domain_event(
    *,
    aggregate_type: str,
    aggregate_id: str | int,
    event_type: str,
    idempotency_key: str,
    payload: dict,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    metadata: dict | None = None,
) -> AlertDomainEventOutbox:
    event, _created = AlertDomainEventOutbox.objects.get_or_create(
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


def publish_alert_outbox_event(event: AlertDomainEventOutbox) -> None:
    if event.published_at:
        return
    try:
        context_value = (event.metadata or {}).get("context", EventContext.ALERTS.value)
        context = EventContext(context_value)
    except Exception:
        context = EventContext.ALERTS

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
        logger.exception("[alerts] Error publicando outbox id=%s", event.pk)
        event.mark_failed(
            str(exc),
            max_retries=_alerts_outbox_retry_config()["max_retries"],
        )


def publish_alert_event_after_commit(
    *,
    event_type: str,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> AlertDomainEventOutbox:
    event_metadata = {
        "context": EventContext.ALERTS.value,
        "priority": int(priority),
        **(metadata or {}),
    }
    aggregate_type = str(event_metadata.get("aggregate_type") or "alert")
    aggregate_id = str(event_metadata.get("aggregate_id") or "") or str((payload or {}).get("alert_id") or "") or str(correlation_id or "")
    idempotency_key = stable_alert_event_key(
        event_type=event_type,
        aggregate_type=aggregate_type or "alert",
        aggregate_id=aggregate_id or "alerts",
        payload=payload or {},
    )
    event = enqueue_alert_domain_event(
        aggregate_type=aggregate_type or "alert",
        aggregate_id=aggregate_id or "alerts",
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=payload or {},
        correlation_id=correlation_id,
        causation_id=causation_id,
        metadata=event_metadata,
    )
    schedule_local_outbox_autopublish(
        event,
        reload_event=lambda event_id: AlertDomainEventOutbox.objects.filter(pk=event_id).first(),
        publish_event=publish_alert_outbox_event,
    )
    return event
