from __future__ import annotations

import logging
from time import monotonic

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from common.domain_events import EventContext, EventPriority, publish_domain_event

from finance.accounts.models.outbox import DomainEventOutbox

logger = logging.getLogger(__name__)

DELIVERY_STATE_KEY = "_vexxo_delivery"


def _local_autopublish_enabled() -> bool:
    return bool(getattr(settings, "DOMAIN_EVENTS_LOCAL_AUTOPUBLISH_ENABLED", False))


def _outbox_retry_config() -> dict:
    return {
        "max_retries": max(1, int(getattr(settings, "ACCOUNTS_OUTBOX_MAX_RETRIES", 10))),
        "base_seconds": max(1, int(getattr(settings, "ACCOUNTS_OUTBOX_RETRY_BASE_SECONDS", 15))),
        "max_seconds": max(1, int(getattr(settings, "ACCOUNTS_OUTBOX_RETRY_MAX_SECONDS", 900))),
        "backoff_factor": max(1, int(getattr(settings, "ACCOUNTS_OUTBOX_RETRY_BACKOFF_FACTOR", 2))),
    }


def _next_outbox_backoff_seconds(event: DomainEventOutbox) -> int:
    config = _outbox_retry_config()
    retry_number = int(event.retry_count or 0) + 1
    base_seconds = config["base_seconds"]
    factor = config["backoff_factor"]
    candidate = base_seconds * (factor ** max(0, retry_number - 1))
    return min(config["max_seconds"], max(base_seconds, int(candidate)))


def _delivery_state(event: DomainEventOutbox) -> dict:
    metadata = dict(event.metadata or {})
    delivery = dict(metadata.get(DELIVERY_STATE_KEY) or {})
    delivery.setdefault("local", {})
    delivery.setdefault("external", {})
    return delivery


def _persist_delivery_state(event: DomainEventOutbox, delivery: dict) -> None:
    metadata = dict(event.metadata or {})
    metadata[DELIVERY_STATE_KEY] = delivery
    event.metadata = metadata
    event.save(update_fields=["metadata"])


def _mark_delivery_phase(event: DomainEventOutbox, *, phase: str, result: str) -> None:
    delivery = _delivery_state(event)
    delivery[str(phase)] = {
        "result": result,
        "at": timezone.now().isoformat(),
    }
    _persist_delivery_state(event, delivery)


def _delivery_phase_completed(event: DomainEventOutbox, *, phase: str) -> bool:
    return str((_delivery_state(event).get(phase) or {}).get("result") or "") == "success"


def _normalize_outbox_metadata(metadata: dict | None = None) -> dict:
    base_metadata = dict(metadata or {})
    correlation_id = str(base_metadata.get("correlation_id") or "").strip()
    causation_id = str(base_metadata.get("causation_id") or "").strip()
    request_id = str(base_metadata.get("request_id") or "").strip()
    if correlation_id:
        base_metadata.setdefault("correlation_id", correlation_id)
    if causation_id:
        base_metadata.setdefault("causation_id", causation_id)
    if request_id:
        base_metadata.setdefault("request_id", request_id)
    return base_metadata


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
    normalized_metadata = _normalize_outbox_metadata(metadata)
    event, _created = DomainEventOutbox.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "event_type": event_type,
            "payload": payload,
            "metadata": normalized_metadata,
            "correlation_id": str(normalized_metadata.get("correlation_id") or "")[:64],
            "causation_id": str(normalized_metadata.get("causation_id") or "")[:64],
            "request_id": str(normalized_metadata.get("request_id") or "")[:64],
        },
    )
    return event


def publish_outbox_event(event: DomainEventOutbox, *, publisher: str = "") -> DomainEventOutbox:
    """
    Publica un evento de outbox en el event bus local.
    Preparado para reemplazar por Kafka/SNS sin tocar use cases.
    """
    if event.published_at:
        return event

    event.last_publish_started_at = timezone.now()
    event.last_publish_result = DomainEventOutbox.PublishResult.RUNNING
    if publisher:
        event.last_publisher = (publisher or "")[:64]
    event.save(update_fields=["last_publish_started_at", "last_publish_result", "last_publisher"])
    started = monotonic()

    try:
        context_value = (event.metadata or {}).get("context", EventContext.SYSTEM.value)
        context = EventContext(context_value)
    except Exception:
        context = EventContext.SYSTEM

    try:
        publish_metadata = dict(event.metadata or {})
        publish_metadata.setdefault("outbox_event_id", str(event.pk))
        publish_metadata.setdefault("projection_event_key", str(event.pk))
        publish_metadata.setdefault("outbox_idempotency_key", str(event.idempotency_key or ""))
        if not _delivery_phase_completed(event, phase="local"):
            publish_domain_event(
                event_type=event.event_type,
                context=context,
                payload=event.payload,
                metadata=publish_metadata,
                priority=EventPriority.NORMAL,
                correlation_id=event.correlation_id or (event.metadata or {}).get("correlation_id"),
                causation_id=event.causation_id or (event.metadata or {}).get("causation_id"),
                include_local=True,
                include_external=False,
                raise_required_listener_errors=True,
            )
            _mark_delivery_phase(event, phase="local", result="success")

        if not _delivery_phase_completed(event, phase="external"):
            publish_domain_event(
                event_type=event.event_type,
                context=context,
                payload=event.payload,
                metadata=publish_metadata,
                priority=EventPriority.NORMAL,
                correlation_id=event.correlation_id or (event.metadata or {}).get("correlation_id"),
                causation_id=event.causation_id or (event.metadata or {}).get("causation_id"),
                include_local=False,
                include_external=True,
            )
            _mark_delivery_phase(event, phase="external", result="success")

        event.last_publish_finished_at = timezone.now()
        event.last_publish_duration_ms = max(0, int((monotonic() - started) * 1000))
        event.last_publish_result = DomainEventOutbox.PublishResult.SUCCESS
        event.mark_published()
    except Exception as exc:
        logger.exception("[accounts] Error publicando outbox id=%s", event.pk)
        event.last_publish_finished_at = timezone.now()
        event.last_publish_duration_ms = max(0, int((monotonic() - started) * 1000))
        event.last_publish_result = DomainEventOutbox.PublishResult.FAILED
        retry_config = _outbox_retry_config()
        event.mark_failed(
            str(exc),
            max_retries=retry_config["max_retries"],
            backoff_seconds=_next_outbox_backoff_seconds(event),
        )
    return event


def publish_after_commit(event: DomainEventOutbox) -> None:
    """
    El request solo deja el evento en outbox; la publicacion real la hace un
    worker dedicado fuera del path web.
    """
    if not event or event.published_at or not _local_autopublish_enabled():
        return None
    if getattr(event, "_local_publish_scheduled", False):
        return None

    event._local_publish_scheduled = True

    def _publish_local_event() -> None:
        fresh = DomainEventOutbox.objects.filter(pk=event.pk).first()
        if fresh is None or fresh.published_at:
            return
        publish_outbox_event(fresh, publisher="local-after-commit")

    transaction.on_commit(_publish_local_event)
    return None
