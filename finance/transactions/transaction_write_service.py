from __future__ import annotations

from django.db import transaction as db_tx

from finance.transactions.actor_context import bind_transaction_actor
from finance.transactions.domain_events import serialize_transaction_state
from finance.transactions.transaction_event_publisher import (
    publish_transaction_change_events,
    publish_transaction_deleted_event,
)
from finance.transactions.transaction_validation_service import apply_tag_selection


def _set_actor(instance, actor) -> None:
    instance._event_actor_id = str(getattr(actor, "id", "") or "")


def save_transaction_with_events(
    *,
    instance,
    actor=None,
    before: dict | None = None,
    created: bool = False,
    event_source: str,
    update_fields=None,
):
    with bind_transaction_actor(actor):
        _set_actor(instance, actor)
        instance._skip_transaction_signal_publication = True
        if update_fields:
            instance.save(update_fields=list(update_fields))
        else:
            instance.save()
        publish_transaction_change_events(
            instance,
            created=created,
            before=before or {},
            source=event_source,
        )
    return instance


@db_tx.atomic
def create_manual_transaction(
    *,
    validated_data: dict,
    actor=None,
    tags_data=None,
    event_source: str = "finance.transactions.transaction_write_service.create",
    budget_context_shared_budget=None,
):
    account = validated_data.get("account")
    if account is not None:
        validated_data["owner"] = account.owner
    from finance.transactions.Models import Transaction

    tx = Transaction(**validated_data)
    tx = save_transaction_with_events(
        instance=tx,
        actor=actor,
        before={},
        created=True,
        event_source=event_source,
    )
    tx = apply_tag_selection(tx, tags_data)
    return tx


@db_tx.atomic
def update_manual_transaction(
    *,
    instance,
    validated_data: dict,
    actor=None,
    tags_data=None,
    event_source: str = "finance.transactions.transaction_write_service.update",
    budget_context_shared_budget=None,
):
    before = serialize_transaction_state(instance)
    previous_category_id = instance.category_id
    changed_values = {
        field: (getattr(instance, f"{field}_id", None) if field in {"account", "category", "vendor", "shared_budget"} else getattr(instance, field, None), value.pk if hasattr(value, "pk") else value)
        for field, value in validated_data.items()
        if hasattr(instance, field) or hasattr(instance, f"{field}_id")
    }
    for attr, value in validated_data.items():
        setattr(instance, attr, value)
    tx = save_transaction_with_events(
        instance=instance,
        actor=actor,
        before=before,
        created=False,
        event_source=event_source,
    )
    tx = apply_tag_selection(instance, tags_data)
    from finance.transactions.Models import TransactionClassificationRevision, TransactionFieldProvenance

    for field, (previous, current) in changed_values.items():
        if previous != current:
            TransactionFieldProvenance.objects.create(
                transaction=tx,
                field_name=field,
                source=TransactionFieldProvenance.Source.USER,
                previous_value=previous,
                current_value=current,
                actor=actor,
            )
    if previous_category_id != tx.category_id:
        TransactionClassificationRevision.objects.create(
            transaction=tx,
            previous_category_id=previous_category_id,
            category_id=tx.category_id,
            source=TransactionFieldProvenance.Source.USER,
            actor=actor,
            reason="manual_correction",
        )
    return tx


@db_tx.atomic
def delete_transaction(*, instance, actor=None, event_source: str = "finance.transactions.transaction_write_service.delete") -> None:
    before = serialize_transaction_state(instance)
    with bind_transaction_actor(actor):
        instance._deleted_pk = instance.pk
        instance._deleted_owner_id = instance.owner_id
        _set_actor(instance, actor)
        instance._skip_transaction_delete_signal_publication = True
        instance.delete()
        publish_transaction_deleted_event(instance, before=before, source=event_source)
