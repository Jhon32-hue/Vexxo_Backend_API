from __future__ import annotations

import hashlib
import json
import logging
import socket

from django.db import models
from django.utils import timezone

from common.domain_events import EventContext, EventPriority, publish_domain_event
from tasks.outbox_autopublish import schedule_local_outbox_autopublish


logger = logging.getLogger(__name__)


def stable_event_key(
    *, namespace: str, event_type: str, aggregate_type: str, aggregate_id: str | int, payload: dict
) -> str:
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
    return f"{namespace}:{digest}"


def enqueue_domain_event(
    *,
    model,
    aggregate_type: str,
    aggregate_id: str | int,
    event_type: str,
    payload: dict,
    idempotency_key: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    metadata: dict | None = None,
):
    event, _created = model.objects.get_or_create(
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


def publish_standard_outbox_event(event, *, context: EventContext) -> None:
    if event.published_at:
        return
    try:
        metadata = dict(event.metadata or {})
        metadata.setdefault("outbox_event_id", str(event.pk))
        metadata.setdefault("projection_event_key", str(event.pk))
        metadata.setdefault("outbox_idempotency_key", str(event.idempotency_key or ""))
        priority_value = metadata.get("priority", int(EventPriority.NORMAL))
        try:
            priority = EventPriority(int(priority_value))
        except Exception:
            priority = EventPriority.NORMAL
        publish_domain_event(
            event_type=event.event_type,
            context=context,
            payload=event.payload,
            metadata=metadata,
            priority=priority,
            correlation_id=event.correlation_id or metadata.get("correlation_id"),
            causation_id=event.causation_id or metadata.get("causation_id"),
            raise_required_listener_errors=True,
        )
        event.mark_published()
    except Exception as exc:
        logger.exception("[%s] Error publicando outbox id=%s", context.value, event.pk)
        event.mark_failed(str(exc))


def enqueue_event_after_commit(
    *,
    model,
    namespace: str,
    context: EventContext,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | int,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
):
    event_metadata = {
        "context": context.value,
        "priority": int(priority),
        **(metadata or {}),
    }
    key = idempotency_key or stable_event_key(
        namespace=namespace,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )
    event = enqueue_domain_event(
        model=model,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        idempotency_key=key,
        correlation_id=correlation_id,
        causation_id=causation_id,
        metadata=event_metadata,
    )
    schedule_local_outbox_autopublish(
        event,
        reload_event=lambda event_id: model.objects.filter(pk=event_id).first(),
        publish_event=lambda fresh: publish_standard_outbox_event(fresh, context=context),
    )
    return event


def publish_pending_events(*, model, context: EventContext, limit: int = 200, worker_id: str = "") -> dict:
    worker_id = str(worker_id or f"{socket.gethostname()}:{context.value}-outbox")[:64]
    stale_threshold = timezone.now() - timezone.timedelta(minutes=15)
    queryset = (
        model.objects.filter(
            models.Q(status__in=[model.Status.PENDING, model.Status.FAILED])
            | models.Q(status=model.Status.PROCESSING, locked_at__lte=stale_threshold)
        )
        .filter(
            models.Q(next_attempt_at__isnull=True)
            | models.Q(next_attempt_at__lte=timezone.now())
            | models.Q(status=model.Status.PROCESSING)
        )
        .order_by("occurred_at")[: max(1, int(limit or 200))]
    )
    summary = {"processed": 0, "failed": 0, "scanned": 0}
    for event in queryset:
        summary["scanned"] += 1
        if not event.claim_for_processing(worker_id=worker_id):
            continue
        publish_standard_outbox_event(event, context=context)
        event.refresh_from_db()
        if event.published_at:
            summary["processed"] += 1
        else:
            summary["failed"] += 1
    return summary
