from common.domain_events import EventContext, EventPriority
from common.outbox_runtime import enqueue_event_after_commit, publish_standard_outbox_event
from finance.debts.models import DebtDomainEventOutbox


def enqueue_debt_event(
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
) -> DebtDomainEventOutbox:
    return enqueue_event_after_commit(
        model=DebtDomainEventOutbox,
        namespace="debtevt",
        context=EventContext.DEBTS,
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


def publish_debt_outbox_event(event: DebtDomainEventOutbox) -> None:
    publish_standard_outbox_event(event, context=EventContext.DEBTS)
