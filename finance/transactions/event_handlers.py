from __future__ import annotations

import logging

from common.domain_events import EventContext, subscribe
from finance.transactions.domain_events import TransactionDomainEventTypes
from finance.transactions.transaction_actions_service import (
    apply_transaction_to_debt_if_any,
    create_over_limit_alert_if_needed,
    reconcile_transaction_financial_update,
)

logger = logging.getLogger(__name__)


def _load_tx(event):
    from finance.transactions.Models.transacciones import Transaction

    transaction_id = (event.payload or {}).get("transaction_id")
    if not transaction_id:
        return None
    return Transaction.objects.filter(pk=transaction_id).select_related("account", "debt", "installment").first()


def _load_contact(contact_id):
    if not contact_id:
        return None
    from contacts.models.contact import Contact

    return Contact.objects.filter(pk=contact_id).first()


def _should_process_transaction_side_effects(event) -> bool:
    payload = event.payload or {}
    countable_now = bool(payload.get("countable_for_ledger"))
    countable_before = bool(payload.get("countable_before"))
    financial_change = payload.get("financial_change") or {}
    if event.type == TransactionDomainEventTypes.TRANSACTION_CREATED:
        return countable_now
    if event.type == TransactionDomainEventTypes.TRANSACTION_CONFIRMED:
        return countable_now
    if event.type == TransactionDomainEventTypes.TRANSACTION_UPDATED:
        return countable_now and not countable_before
    if event.type == TransactionDomainEventTypes.TRANSACTION_FINANCIAL_UPDATED:
        return financial_change.get("kind") == "updated_while_countable"
    return False


@subscribe(TransactionDomainEventTypes.TRANSACTION_CREATED, contexts=[EventContext.TRANSACTIONS], required=True)
@subscribe(TransactionDomainEventTypes.TRANSACTION_UPDATED, contexts=[EventContext.TRANSACTIONS], required=True)
@subscribe(TransactionDomainEventTypes.TRANSACTION_FINANCIAL_UPDATED, contexts=[EventContext.TRANSACTIONS], required=True)
@subscribe(TransactionDomainEventTypes.TRANSACTION_CONFIRMED, contexts=[EventContext.TRANSACTIONS], required=True)
def handle_transaction_side_effects(event):
    if not _should_process_transaction_side_effects(event):
        return
    tx = _load_tx(event)
    if not tx:
        return
    if event.type != TransactionDomainEventTypes.TRANSACTION_FINANCIAL_UPDATED:
        apply_transaction_to_debt_if_any(tx)
    else:
        reconcile_transaction_financial_update(tx=tx, before=(event.payload or {}).get("before") or {})
    create_over_limit_alert_if_needed(tx)


@subscribe(TransactionDomainEventTypes.PARTICIPANT_CREATED, contexts=[EventContext.TRANSACTIONS], required=True)
@subscribe(TransactionDomainEventTypes.PARTICIPANT_UPDATED, contexts=[EventContext.TRANSACTIONS], required=True)
@subscribe(TransactionDomainEventTypes.PARTICIPANT_DELETED, contexts=[EventContext.TRANSACTIONS], required=True)
@subscribe(TransactionDomainEventTypes.PARTICIPANT_SETTLED, contexts=[EventContext.TRANSACTIONS], required=True)
def handle_participant_side_effects(event):
    contact_id = (event.payload or {}).get("contact_id")
    contact = _load_contact(contact_id)
    if not contact:
        return
    if hasattr(contact, "recalc_net_balance") and callable(contact.recalc_net_balance):
        contact.recalc_net_balance()

