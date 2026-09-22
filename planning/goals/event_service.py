from common.domain_events import EventContext, EventPriority
from common.outbox_runtime import enqueue_event_after_commit, publish_standard_outbox_event
from planning.goals.models import GoalDomainEventOutbox


def enqueue_goal_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str | int,
    payload: dict,
    metadata: dict | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
) -> GoalDomainEventOutbox:
    return enqueue_event_after_commit(
        model=GoalDomainEventOutbox,
        namespace="goalevt",
        context=EventContext.GOALS,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        metadata=metadata,
        priority=priority,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
    )


def publish_goal_outbox_event(event: GoalDomainEventOutbox) -> None:
    publish_standard_outbox_event(event, context=EventContext.GOALS)
