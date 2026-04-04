from __future__ import annotations

from collections.abc import Mapping

from finance.transactions.Models.transacciones import Transaction, TransactionParticipant

LEDGER_COUNTABLE_STATUSES = {
    Transaction.Status.POSTED,
    Transaction.Status.RECONCILED,
}
PARTICIPANT_ACTIVE_STATUSES = {
    TransactionParticipant.Status.ACTIVE,
    TransactionParticipant.Status.PENDING,
    TransactionParticipant.Status.PARTIAL,
}


def normalize_transaction_state(*, status: str, confirmed: bool, affects_balance: bool = True) -> dict:
    resolved_status = str(status or Transaction.Status.POSTED)
    resolved_confirmed = bool(confirmed)
    resolved_affects_balance = bool(affects_balance)

    if resolved_confirmed and resolved_status == Transaction.Status.PENDING:
        resolved_status = Transaction.Status.POSTED

    if resolved_status in LEDGER_COUNTABLE_STATUSES:
        resolved_confirmed = True

    if resolved_status in {Transaction.Status.CANCELED, Transaction.Status.FAILED}:
        resolved_affects_balance = False

    return {
        "status": resolved_status,
        "confirmed": resolved_confirmed,
        "affects_balance": resolved_affects_balance,
    }


def is_transaction_countable_for_ledger(tx_or_state) -> bool:
    if isinstance(tx_or_state, Mapping):
        status = str(tx_or_state.get("status") or "")
        confirmed = bool(tx_or_state.get("confirmed"))
        affects_balance = bool(tx_or_state.get("affects_balance", True))
    else:
        status = str(getattr(tx_or_state, "status", "") or "")
        confirmed = bool(getattr(tx_or_state, "confirmed", False))
        affects_balance = bool(getattr(tx_or_state, "affects_balance", True))
    return bool(status in LEDGER_COUNTABLE_STATUSES and confirmed and affects_balance)


def is_participant_active(participant_or_state) -> bool:
    status = str(
        participant_or_state.get("status")
        if isinstance(participant_or_state, Mapping)
        else getattr(participant_or_state, "status", "")
    )
    return status in PARTICIPANT_ACTIVE_STATUSES
