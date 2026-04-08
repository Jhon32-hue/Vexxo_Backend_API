from __future__ import annotations

from datetime import date, datetime

from common.domain_events import EventContext, EventNames
from finance.transactions.actor_context import get_current_transaction_actor_id
from finance.transactions.transaction_state_service import is_transaction_countable_for_ledger


class TransactionDomainEventTypes:
    TRANSACTION_CREATED = EventNames.TRANSACTION_CREATED
    TRANSACTION_UPDATED = EventNames.TRANSACTION_UPDATED
    TRANSACTION_FINANCIAL_UPDATED = EventNames.TRANSACTION_FINANCIAL_UPDATED
    TRANSACTION_DELETED = EventNames.TRANSACTION_DELETED
    TRANSACTION_IMPORTED = EventNames.TRANSACTION_IMPORTED
    TRANSACTION_INTAKE_BATCH_RECEIVED = EventNames.TRANSACTION_INTAKE_BATCH_RECEIVED
    TRANSACTION_INTAKE_BATCH_APPLIED = EventNames.TRANSACTION_INTAKE_BATCH_APPLIED
    TRANSACTION_INTAKE_BATCH_FAILED = EventNames.TRANSACTION_INTAKE_BATCH_FAILED
    TRANSACTION_INTAKE_ROW_DUPLICATE_DETECTED = EventNames.TRANSACTION_INTAKE_ROW_DUPLICATE_DETECTED
    TRANSACTION_RECONCILED = EventNames.TRANSACTION_RECONCILED
    TRANSACTION_CORRECTED = EventNames.TRANSACTION_CORRECTED
    TRANSACTION_REVERSED = EventNames.TRANSACTION_REVERSED
    TRANSACTION_RECONCILIATION_ISSUE_RESOLVED = EventNames.TRANSACTION_RECONCILIATION_ISSUE_RESOLVED
    TRANSACTION_CONFIRMED = EventNames.TRANSACTION_CONFIRMED
    TRANSACTION_ACCOUNT_REASSIGNED = EventNames.TRANSACTION_ACCOUNT_REASSIGNED
    TRANSACTION_REIMBURSEMENT_RECORDED = EventNames.TRANSACTION_REIMBURSEMENT_RECORDED
    PARTICIPANT_CREATED = EventNames.TRANSACTION_PARTICIPANT_CREATED
    PARTICIPANT_UPDATED = EventNames.TRANSACTION_PARTICIPANT_UPDATED
    PARTICIPANT_DELETED = EventNames.TRANSACTION_PARTICIPANT_DELETED
    PARTICIPANT_SETTLED = EventNames.TRANSACTION_PARTICIPANT_SETTLED
    SCHEDULED_PAYMENT_CREATED = EventNames.TRANSACTION_SCHEDULED_PAYMENT_CREATED
    SCHEDULED_PAYMENT_UPDATED = EventNames.TRANSACTION_SCHEDULED_PAYMENT_UPDATED
    SCHEDULED_PAYMENT_DELETED = EventNames.TRANSACTION_SCHEDULED_PAYMENT_DELETED
    SCHEDULED_PAYMENT_PAID = EventNames.TRANSACTION_SCHEDULED_PAYMENT_PAID


def _base_metadata(source: str, metadata: dict | None = None) -> dict:
    return {
        "context": EventContext.TRANSACTIONS.value,
        "source": source,
        **(metadata or {}),
    }


def _serialize_dateish(value) -> str:
    if not value:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def build_transaction_payload(tx, *, before: dict | None = None, after: dict | None = None) -> dict:
    state = after or serialize_transaction_state(tx)
    previous = before or {}
    financial_change = _build_financial_change(previous, state)
    return {
        "transaction_id": str(tx.pk),
        "owner_id": str(tx.owner_id),
        "account_owner_id": str(getattr(tx.account, "owner_id", tx.owner_id) or tx.owner_id),
        "account_id": str(tx.account_id) if tx.account_id else "",
        "category_id": str(tx.category_id) if tx.category_id else "",
        "vendor_id": str(tx.vendor_id) if tx.vendor_id else "",
        "debt_id": str(tx.debt_id) if tx.debt_id else "",
        "installment_id": str(tx.installment_id) if tx.installment_id else "",
        "scheduled_payment_id": str(tx.scheduled_payment_id) if tx.scheduled_payment_id else "",
        "payment_intent_id": str(tx.payment_intent_id) if tx.payment_intent_id else "",
        "parent_id": str(tx.parent_id) if tx.parent_id else "",
        "type": tx.type,
        "status": tx.status,
        "confirmed": tx.confirmed,
        "affects_balance": tx.affects_balance,
        "amount": str(tx.amount),
        "date": _serialize_dateish(tx.date),
        "source": tx.source,
        "provider": tx.provider,
        "external_id": tx.external_id,
        "shared_account": bool(getattr(tx.account, "owner_id", tx.owner_id) != tx.owner_id or getattr(tx.account, "ownership", "") == "shared"),
        "actor_user_id": str(getattr(tx, "_event_actor_id", "") or get_current_transaction_actor_id() or ""),
        "is_reimbursable": tx.is_reimbursable,
        "reimbursed": tx.reimbursed,
        "reimbursement_transaction_id": str(tx.reimbursement_transaction_id) if tx.reimbursement_transaction_id else "",
        "countable_for_ledger": is_transaction_countable_for_ledger(tx),
        "countable_before": is_transaction_countable_for_ledger(previous),
        "financial_change": financial_change,
        "before": previous,
        "after": state,
    }


def serialize_transaction_state(tx) -> dict:
    return {
        "status": tx.status,
        "confirmed": tx.confirmed,
        "affects_balance": tx.affects_balance,
        "account_id": str(tx.account_id) if tx.account_id else "",
        "category_id": str(tx.category_id) if tx.category_id else "",
        "vendor_id": str(tx.vendor_id) if tx.vendor_id else "",
        "debt_id": str(tx.debt_id) if tx.debt_id else "",
        "installment_id": str(tx.installment_id) if tx.installment_id else "",
        "payment_intent_id": str(tx.payment_intent_id) if tx.payment_intent_id else "",
        "provider": tx.provider,
        "external_id": tx.external_id,
        "scheduled_payment_id": str(tx.scheduled_payment_id) if tx.scheduled_payment_id else "",
        "reimbursed": tx.reimbursed,
        "reimbursement_transaction_id": str(tx.reimbursement_transaction_id) if tx.reimbursement_transaction_id else "",
        "amount": str(tx.amount),
        "date": _serialize_dateish(tx.date),
        "type": tx.type,
    }


FINANCIAL_TRACKED_FIELDS = [
    "account_id",
    "amount",
    "date",
    "type",
    "status",
    "confirmed",
    "affects_balance",
    "debt_id",
    "installment_id",
    "scheduled_payment_id",
    "payment_intent_id",
]


def _build_financial_change(before: dict | None, after: dict | None) -> dict:
    before = before or {}
    after = after or {}
    changed_fields = [
        field
        for field in FINANCIAL_TRACKED_FIELDS
        if str(before.get(field, "")) != str(after.get(field, ""))
    ]
    countable_before = is_transaction_countable_for_ledger(before)
    countable_after = is_transaction_countable_for_ledger(after)
    if not changed_fields and countable_before == countable_after:
        kind = "cosmetic"
    elif not countable_before and countable_after:
        kind = "became_countable"
    elif countable_before and not countable_after:
        kind = "stopped_countable"
    elif countable_before and countable_after:
        kind = "updated_while_countable"
    else:
        kind = "updated_while_non_countable"
    return {
        "kind": kind,
        "is_financial": bool(changed_fields or countable_before != countable_after),
        "changed_fields": changed_fields,
        "countable_before": countable_before,
        "countable_after": countable_after,
    }


def serialize_scheduled_payment_state(sp) -> dict:
    return {
        "status": sp.status,
        "amount": str(sp.amount),
        "due_date": _serialize_dateish(sp.due_date),
        "account_id": str(sp.account_id) if sp.account_id else "",
        "vendor_id": str(sp.vendor_id) if sp.vendor_id else "",
    }


def build_scheduled_payment_payload(sp, *, before: dict | None = None) -> dict:
    return {
        "scheduled_payment_id": str(sp.pk),
        "owner_id": str(sp.owner_id),
        "account_id": str(sp.account_id) if sp.account_id else "",
        "debt_id": str(sp.debt_id) if sp.debt_id else "",
        "installment_id": str(sp.installment_id) if sp.installment_id else "",
        "status": sp.status,
        "amount": str(sp.amount),
        "due_date": _serialize_dateish(sp.due_date),
        "before": before or {},
        "after": serialize_scheduled_payment_state(sp),
    }


def serialize_participant_state(participant) -> dict:
    return {
        "status": participant.status,
        "direction": participant.direction,
        "contact_id": str(participant.contact_id) if participant.contact_id else "",
        "linked_user_id": str(participant.linked_user_id) if participant.linked_user_id else "",
        "share_amount": str(participant.share_amount),
        "paid_amount": str(participant.paid_amount),
    }


def build_participant_payload(participant, *, before: dict | None = None) -> dict:
    return {
        "participant_id": str(participant.pk),
        "owner_id": str(participant.owner_id),
        "transaction_id": str(participant.transaction_id),
        "contact_id": str(participant.contact_id) if participant.contact_id else "",
        "linked_user_id": str(participant.linked_user_id) if participant.linked_user_id else "",
        "direction": participant.direction,
        "status": participant.status,
        "invite_status": participant.invite_status,
        "display_name": participant.display_name,
        "actor_user_id": str(getattr(participant, "_event_actor_id", "") or get_current_transaction_actor_id() or ""),
        "share_amount": str(participant.share_amount),
        "paid_amount": str(participant.paid_amount),
        "before": before or {},
        "after": serialize_participant_state(participant),
    }


__all__ = [
    "TransactionDomainEventTypes",
    "_base_metadata",
    "build_transaction_payload",
    "build_scheduled_payment_payload",
    "build_participant_payload",
    "serialize_transaction_state",
    "serialize_scheduled_payment_state",
    "serialize_participant_state",
]
