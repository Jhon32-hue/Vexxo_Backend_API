from __future__ import annotations

from datetime import datetime
import logging

from common.domain_events import EventContext, subscribe
from finance.budgets.models import SharedBudgetTransactionLink
from finance.budgets.services import (
    evaluate_budget_thresholds_for_owner_month_by_id,
    evaluate_shared_budget_thresholds_for_budget_ids,
)
from payments.payment_intents.domain_events import PaymentDomainEventTypes
from finance.transactions.domain_events import TransactionDomainEventTypes
from finance.transactions.transaction_state_service import is_transaction_countable_for_ledger

logger = logging.getLogger(__name__)


def _parse_month_from_dateish(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m")
    except ValueError:
        try:
            return raw[:7]
        except Exception:  # pragma: no cover - defensive branch
            return None


def _transaction_relevant_months(payload: dict) -> set[str]:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    months = {
        month
        for month in (
            _parse_month_from_dateish(payload.get("date")),
            _parse_month_from_dateish(before.get("date")),
            _parse_month_from_dateish(after.get("date")),
        )
        if month
    }
    return months


def _should_recalculate_budget(payload: dict) -> bool:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    expense_involved = any(
        state.get("type") == "expense"
        for state in (before, after, payload)
        if isinstance(state, dict)
    )
    if not expense_involved:
        return False
    if is_transaction_countable_for_ledger(before) or is_transaction_countable_for_ledger(after):
        return True
    if is_transaction_countable_for_ledger(payload):
        return True
    financial_change = payload.get("financial_change") or {}
    return bool(financial_change.get("is_financial"))


def _linked_shared_budget_ids(transaction_id: str | int | None) -> list[int]:
    raw_id = str(transaction_id or "").strip()
    if not raw_id:
        return []
    return list(
        SharedBudgetTransactionLink.objects.filter(transaction_id=raw_id).values_list("shared_budget_id", flat=True).distinct()
    )


def _payload_shared_budget_ids(payload: dict) -> set[int]:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    raw_values = {
        payload.get("shared_budget_id"),
        before.get("shared_budget_id"),
        after.get("shared_budget_id"),
    }
    ids = set()
    for value in raw_values:
        raw = str(value or "").strip()
        if raw.isdigit():
            ids.add(int(raw))
    return ids


@subscribe(TransactionDomainEventTypes.TRANSACTION_CREATED, contexts=[EventContext.TRANSACTIONS])
@subscribe(TransactionDomainEventTypes.TRANSACTION_UPDATED, contexts=[EventContext.TRANSACTIONS])
@subscribe(TransactionDomainEventTypes.TRANSACTION_FINANCIAL_UPDATED, contexts=[EventContext.TRANSACTIONS])
@subscribe(TransactionDomainEventTypes.TRANSACTION_CONFIRMED, contexts=[EventContext.TRANSACTIONS])
@subscribe(TransactionDomainEventTypes.TRANSACTION_DELETED, contexts=[EventContext.TRANSACTIONS])
@subscribe(TransactionDomainEventTypes.TRANSACTION_REVERSED, contexts=[EventContext.TRANSACTIONS])
@subscribe(TransactionDomainEventTypes.TRANSACTION_CORRECTED, contexts=[EventContext.TRANSACTIONS])
def handle_budget_threshold_recalculation(event):
    payload = event.payload or {}
    if not _should_recalculate_budget(payload):
        return
    owner_id = payload.get("owner_id") or payload.get("account_owner_id")
    months = _transaction_relevant_months(payload)
    if owner_id and months:
        for month in months:
            try:
                evaluate_budget_thresholds_for_owner_month_by_id(
                    owner_id=owner_id,
                    month=month,
                    source=f"finance.budgets.event_handlers.{event.type}",
                )
            except Exception:  # pragma: no cover - observability branch
                logger.exception(
                    "[budgets] error recalculating personal thresholds owner=%s month=%s event=%s",
                    owner_id,
                    month,
                    event.type,
                )

    linked_budget_ids = set(_linked_shared_budget_ids(payload.get("transaction_id"))) | _payload_shared_budget_ids(payload)
    if not linked_budget_ids:
        return
    try:
        evaluate_shared_budget_thresholds_for_budget_ids(
            budget_ids=sorted(linked_budget_ids),
            source=f"finance.budgets.event_handlers.{event.type}",
        )
    except Exception:  # pragma: no cover - observability branch
        logger.exception(
            "[budgets] error recalculating shared thresholds budgets=%s event=%s",
            linked_budget_ids,
            event.type,
        )


def _payment_template_months(payload: dict) -> set[str]:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    return {
        month
        for month in (
            _parse_month_from_dateish(payload.get("next_run_at")),
            _parse_month_from_dateish(before.get("next_run_at")),
            _parse_month_from_dateish(after.get("next_run_at")),
        )
        if month
    }


@subscribe(PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_CREATED, contexts=[EventContext.PAYMENTS])
@subscribe(PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_UPDATED, contexts=[EventContext.PAYMENTS])
@subscribe(PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_DELETED, contexts=[EventContext.PAYMENTS])
@subscribe(PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_ACTIVATED, contexts=[EventContext.PAYMENTS])
@subscribe(PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_DEACTIVATED, contexts=[EventContext.PAYMENTS])
def handle_payment_template_budget_recalculation(event):
    payload = event.payload or {}
    owner_id = payload.get("owner_id")
    months = _payment_template_months(payload)
    if owner_id and months:
        for month in months:
            try:
                evaluate_budget_thresholds_for_owner_month_by_id(
                    owner_id=owner_id,
                    month=month,
                    source=f"finance.budgets.event_handlers.{event.type}",
                )
            except Exception:  # pragma: no cover - observability branch
                logger.exception(
                    "[budgets] error recalculating template-driven committed thresholds owner=%s month=%s event=%s",
                    owner_id,
                    month,
                    event.type,
                )
    shared_budget_ids = _payload_shared_budget_ids(payload)
    if not shared_budget_ids:
        return
    try:
        evaluate_shared_budget_thresholds_for_budget_ids(
            budget_ids=sorted(shared_budget_ids),
            source=f"finance.budgets.event_handlers.{event.type}",
        )
    except Exception:  # pragma: no cover - observability branch
        logger.exception(
            "[budgets] error recalculating template-driven shared thresholds budgets=%s event=%s",
            shared_budget_ids,
            event.type,
        )
