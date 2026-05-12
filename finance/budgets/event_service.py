from __future__ import annotations

from django.db import transaction

from common.domain_events import EventContext, EventPriority, publish_domain_event


def publish_budget_event_after_commit(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | int,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    include_external: bool = False,
) -> None:
    event_metadata = {
        "context": EventContext.BUDGETS.value,
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        **(metadata or {}),
    }
    if correlation_id:
        event_metadata.setdefault("correlation_id", correlation_id)
    if causation_id:
        event_metadata.setdefault("causation_id", causation_id)

    def _publish() -> None:
        publish_domain_event(
            event_type=event_type,
            context=EventContext.BUDGETS,
            payload=payload,
            metadata=event_metadata,
            priority=priority,
            correlation_id=correlation_id,
            causation_id=causation_id,
            include_external=include_external,
        )

    transaction.on_commit(_publish)
