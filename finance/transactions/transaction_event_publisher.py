from __future__ import annotations

from finance.transactions.actor_context import get_current_transaction_actor_id
from finance.transactions.domain_events import (
    TransactionDomainEventTypes,
    _base_metadata,
    build_transaction_payload,
)
from finance.transactions.event_service import publish_transaction_event_after_commit


def publish_transaction_change_events(
    tx,
    *,
    created: bool,
    before: dict | None = None,
    source: str,
) -> dict:
    before = before or {}
    payload = build_transaction_payload(tx, before=before)
    event_type = (
        TransactionDomainEventTypes.TRANSACTION_CREATED
        if created
        else TransactionDomainEventTypes.TRANSACTION_UPDATED
    )
    publish_transaction_event_after_commit(
        event_type=event_type,
        payload=payload,
        metadata=_base_metadata(
            source,
            metadata={"aggregate_type": "transaction", "aggregate_id": str(tx.pk)},
        ),
    )
    financial_change = payload.get("financial_change") or {}
    if (
        not created
        and financial_change.get("is_financial")
        and financial_change.get("kind") != "became_countable"
    ):
        publish_transaction_event_after_commit(
            event_type=TransactionDomainEventTypes.TRANSACTION_FINANCIAL_UPDATED,
            payload=payload,
            metadata=_base_metadata(
                f"{source}.financial",
                metadata={"aggregate_type": "transaction", "aggregate_id": str(tx.pk)},
            ),
        )
    if not created and not before.get("confirmed") and tx.confirmed:
        publish_transaction_event_after_commit(
            event_type=TransactionDomainEventTypes.TRANSACTION_CONFIRMED,
            payload=payload,
            metadata=_base_metadata(
                f"{source}.confirmed",
                metadata={"aggregate_type": "transaction", "aggregate_id": str(tx.pk)},
            ),
        )
    return payload


def publish_transaction_deleted_event(instance, *, before: dict | None = None, source: str) -> dict:
    transaction_id = str(getattr(instance, "_deleted_pk", None) or instance.pk or "")
    owner_id = str(getattr(instance, "_deleted_owner_id", None) or instance.owner_id or "")
    payload = {
        "transaction_id": transaction_id,
        "owner_id": owner_id,
        "actor_user_id": str(getattr(instance, "_event_actor_id", "") or get_current_transaction_actor_id() or ""),
        "before": before or {},
    }
    publish_transaction_event_after_commit(
        event_type=TransactionDomainEventTypes.TRANSACTION_DELETED,
        payload=payload,
        metadata=_base_metadata(
            source,
            metadata={"aggregate_type": "transaction", "aggregate_id": transaction_id},
        ),
    )
    return payload
