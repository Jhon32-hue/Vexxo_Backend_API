from __future__ import annotations

from common.domain_events import EventContext, EventPriority
from common.outbox_runtime import enqueue_event_after_commit
from social.shared_expenses.models import SharedExpense, SharedExpenseDomainEventOutbox


def enqueue_shared_expense_event(
    *,
    expense: SharedExpense,
    event_type: str,
    action: str,
    actor_id: int | str,
    request_id: str = "",
    extra: dict | None = None,
):
    payload = {
        "shared_expense_id": str(expense.public_id),
        "transaction_id": expense.transaction_id,
        "owner_id": expense.owner_id,
        "status": expense.status,
        "version": expense.version,
        "action": action,
        **(extra or {}),
    }
    return enqueue_event_after_commit(
        model=SharedExpenseDomainEventOutbox,
        namespace="shared-expense",
        context=EventContext.SHARED_EXPENSES,
        event_type=event_type,
        aggregate_type="shared_expense",
        aggregate_id=expense.public_id,
        payload=payload,
        metadata={
            "actor_id": str(actor_id or ""),
            "request_id": str(request_id or "")[:64],
        },
        priority=EventPriority.NORMAL,
        idempotency_key=f"shared-expense:{expense.public_id}:v{expense.version}:{action}",
    )
