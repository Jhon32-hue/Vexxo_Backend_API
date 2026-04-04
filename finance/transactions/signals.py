from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from finance.transactions.Models.transacciones import ScheduledPayment, Transaction, TransactionParticipant
from finance.transactions.domain_events import (
    TransactionDomainEventTypes,
    _base_metadata,
    build_participant_payload,
    build_scheduled_payment_payload,
    build_transaction_payload,
    serialize_participant_state,
    serialize_scheduled_payment_state,
    serialize_transaction_state,
)
from finance.transactions.event_service import publish_transaction_event_after_commit
from finance.transactions.actor_context import get_current_transaction_actor_id


def _capture_previous_state(instance, serializer):
    if not instance.pk:
        setattr(instance, "_previous_state", {})
        return
    previous = instance.__class__.objects.filter(pk=instance.pk).first()
    setattr(instance, "_previous_state", serializer(previous) if previous else {})


def _publish(event_type: str, payload: dict, *, aggregate_type: str, aggregate_id: str | int, source: str) -> None:
    publish_transaction_event_after_commit(
        event_type=event_type,
        payload=payload,
        metadata=_base_metadata(
            source,
            metadata={"aggregate_type": aggregate_type, "aggregate_id": str(aggregate_id)},
        ),
    )


@receiver(pre_save, sender=Transaction)
def capture_transaction_previous_state(sender, instance: Transaction, **kwargs):
    _capture_previous_state(instance, serialize_transaction_state)


@receiver(post_save, sender=Transaction)
def enqueue_transaction_events(sender, instance: Transaction, created: bool, **kwargs):
    before = getattr(instance, "_previous_state", {}) or {}
    payload = build_transaction_payload(instance, before=before)
    event_type = (
        TransactionDomainEventTypes.TRANSACTION_CREATED
        if created
        else TransactionDomainEventTypes.TRANSACTION_UPDATED
    )
    _publish(
        event_type,
        payload,
        aggregate_type="transaction",
        aggregate_id=instance.pk,
        source="finance.transactions.signals.enqueue_transaction_events",
    )
    financial_change = payload.get("financial_change") or {}
    if (
        not created
        and financial_change.get("is_financial")
        and financial_change.get("kind") != "became_countable"
    ):
        _publish(
            TransactionDomainEventTypes.TRANSACTION_FINANCIAL_UPDATED,
            payload,
            aggregate_type="transaction",
            aggregate_id=instance.pk,
            source="finance.transactions.signals.enqueue_transaction_events.financial",
        )
    if not created and not before.get("confirmed") and instance.confirmed:
        _publish(
            TransactionDomainEventTypes.TRANSACTION_CONFIRMED,
            payload,
            aggregate_type="transaction",
            aggregate_id=instance.pk,
            source="finance.transactions.signals.enqueue_transaction_events.confirmed",
        )


@receiver(pre_delete, sender=Transaction)
def capture_transaction_delete_state(sender, instance: Transaction, **kwargs):
    setattr(instance, "_delete_state", serialize_transaction_state(instance))


@receiver(post_delete, sender=Transaction)
def enqueue_transaction_delete(sender, instance: Transaction, **kwargs):
    payload = {
        "transaction_id": str(instance.pk),
        "owner_id": str(instance.owner_id),
        "actor_user_id": str(getattr(instance, "_event_actor_id", "") or get_current_transaction_actor_id() or ""),
        "before": getattr(instance, "_delete_state", {}) or {},
    }
    _publish(
        TransactionDomainEventTypes.TRANSACTION_DELETED,
        payload,
        aggregate_type="transaction",
        aggregate_id=instance.pk,
        source="finance.transactions.signals.enqueue_transaction_delete",
    )


@receiver(pre_save, sender=TransactionParticipant)
def capture_participant_previous_state(sender, instance: TransactionParticipant, **kwargs):
    _capture_previous_state(instance, serialize_participant_state)


@receiver(post_save, sender=TransactionParticipant)
def enqueue_participant_events(sender, instance: TransactionParticipant, created: bool, **kwargs):
    before = getattr(instance, "_previous_state", {}) or {}
    payload = build_participant_payload(instance, before=before)
    event_type = (
        TransactionDomainEventTypes.PARTICIPANT_CREATED
        if created
        else TransactionDomainEventTypes.PARTICIPANT_UPDATED
    )
    _publish(
        event_type,
        payload,
        aggregate_type="participant",
        aggregate_id=instance.pk,
        source="finance.transactions.signals.enqueue_participant_events",
    )
    if not created and before.get("status") != TransactionParticipant.Status.SETTLED and instance.status == TransactionParticipant.Status.SETTLED:
        _publish(
            TransactionDomainEventTypes.PARTICIPANT_SETTLED,
            payload,
            aggregate_type="participant",
            aggregate_id=instance.pk,
            source="finance.transactions.signals.enqueue_participant_events.settled",
        )


@receiver(pre_delete, sender=TransactionParticipant)
def capture_participant_delete_state(sender, instance: TransactionParticipant, **kwargs):
    setattr(instance, "_delete_state", serialize_participant_state(instance))


@receiver(post_delete, sender=TransactionParticipant)
def enqueue_participant_delete(sender, instance: TransactionParticipant, **kwargs):
    payload = {
        "participant_id": str(instance.pk),
        "owner_id": str(instance.owner_id),
        "contact_id": str(instance.contact_id) if instance.contact_id else "",
        "actor_user_id": str(getattr(instance, "_event_actor_id", "") or get_current_transaction_actor_id() or ""),
        "before": getattr(instance, "_delete_state", {}) or {},
    }
    _publish(
        TransactionDomainEventTypes.PARTICIPANT_DELETED,
        payload,
        aggregate_type="participant",
        aggregate_id=instance.pk,
        source="finance.transactions.signals.enqueue_participant_delete",
    )


@receiver(pre_save, sender=ScheduledPayment)
def capture_scheduled_payment_previous_state(sender, instance: ScheduledPayment, **kwargs):
    _capture_previous_state(instance, serialize_scheduled_payment_state)


@receiver(post_save, sender=ScheduledPayment)
def enqueue_scheduled_payment_events(sender, instance: ScheduledPayment, created: bool, **kwargs):
    before = getattr(instance, "_previous_state", {}) or {}
    payload = build_scheduled_payment_payload(instance, before=before)
    event_type = (
        TransactionDomainEventTypes.SCHEDULED_PAYMENT_CREATED
        if created
        else TransactionDomainEventTypes.SCHEDULED_PAYMENT_UPDATED
    )
    _publish(
        event_type,
        payload,
        aggregate_type="scheduled_payment",
        aggregate_id=instance.pk,
        source="finance.transactions.signals.enqueue_scheduled_payment_events",
    )
    if not created and before.get("status") != ScheduledPayment.Status.PAID and instance.status == ScheduledPayment.Status.PAID:
        _publish(
            TransactionDomainEventTypes.SCHEDULED_PAYMENT_PAID,
            payload,
            aggregate_type="scheduled_payment",
            aggregate_id=instance.pk,
            source="finance.transactions.signals.enqueue_scheduled_payment_events.paid",
        )


@receiver(pre_delete, sender=ScheduledPayment)
def capture_scheduled_payment_delete_state(sender, instance: ScheduledPayment, **kwargs):
    setattr(instance, "_delete_state", serialize_scheduled_payment_state(instance))


@receiver(post_delete, sender=ScheduledPayment)
def enqueue_scheduled_payment_delete(sender, instance: ScheduledPayment, **kwargs):
    payload = {
        "scheduled_payment_id": str(instance.pk),
        "owner_id": str(instance.owner_id),
        "actor_user_id": str(getattr(instance, "_event_actor_id", "") or get_current_transaction_actor_id() or ""),
        "before": getattr(instance, "_delete_state", {}) or {},
    }
    _publish(
        TransactionDomainEventTypes.SCHEDULED_PAYMENT_DELETED,
        payload,
        aggregate_type="scheduled_payment",
        aggregate_id=instance.pk,
        source="finance.transactions.signals.enqueue_scheduled_payment_delete",
    )
