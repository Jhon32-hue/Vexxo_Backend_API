from __future__ import annotations

from decimal import Decimal

from django.db import transaction as db_tx
from django.utils import timezone
from django.utils.dateparse import parse_date

from finance.transactions.Models import Transaction, TransactionReconciliationIssue
from finance.transactions.event_service import publish_transaction_event_after_commit
from finance.transactions.transaction_intake_service import (
    _ensure_source_link,
    _resolve_account,
    _sync_source_link,
    _update_transaction_from_intake,
)
from finance.transactions.transaction_write_service import create_manual_transaction


def _normalized_from_issue(issue: TransactionReconciliationIssue) -> dict:
    details = issue.details or {}
    normalized = details.get("normalized") or {}
    if normalized:
        return dict(normalized)
    if issue.source_link_id and issue.source_link and issue.source_link.last_normalized_payload:
        return dict(issue.source_link.last_normalized_payload or {})
    raise ValueError("El issue no tiene payload normalizado suficiente para resolverse.")


def _publish_issue_resolved(issue: TransactionReconciliationIssue) -> None:
    publish_transaction_event_after_commit(
        event_type="transactions.reconciliation.issue.resolved.v1",
        payload={
            "issue_id": str(issue.pk),
            "transaction_id": str(issue.transaction_id),
            "status": issue.status,
            "issue_type": issue.issue_type,
            "resolution_action": issue.resolution_action,
            "resolved_by_id": str(issue.resolved_by_id or ""),
            "resolution_transaction_id": str(issue.resolution_transaction_id or ""),
        },
        metadata={
            "context": "transactions",
            "source": "finance.transactions.transaction_reconciliation_service.resolve_reconciliation_issue",
            "aggregate_type": "transaction_reconciliation_issue",
            "aggregate_id": str(issue.pk),
        },
    )


def _sync_latest_provider_state(issue: TransactionReconciliationIssue, normalized: dict) -> None:
    if issue.source_link_id and issue.source_link:
        _sync_source_link(source_link=issue.source_link, normalized=normalized, tx=issue.transaction)
    elif normalized:
        _ensure_source_link(tx=issue.transaction, normalized=normalized)


def _inverse_type(tx_type: str) -> str:
    if tx_type == Transaction.Type.EXPENSE:
        return Transaction.Type.INCOME
    if tx_type == Transaction.Type.INCOME:
        return Transaction.Type.EXPENSE
    raise ValueError("Solo se soportan reversos formales para expense/income en esta pasada.")


def _build_adjustment_transaction(*, issue: TransactionReconciliationIssue, normalized: dict):
    before = (issue.details or {}).get("before") or {}
    after = (issue.details or {}).get("after") or {}
    tx = issue.transaction

    if tx.type not in {Transaction.Type.EXPENSE, Transaction.Type.INCOME}:
        raise ValueError("Solo se soportan ajustes compensatorios para expense/income.")
    if str(before.get("account_id", "")) != str(after.get("account_id", "")) or str(after.get("account_id", "")) != str(tx.account_id):
        raise ValueError("El ajuste compensatorio simple no soporta cambio de cuenta.")
    if str(before.get("type", "")) != str(after.get("type", "")) or str(after.get("type", "")) != str(tx.type):
        raise ValueError("El ajuste compensatorio simple no soporta cambio de tipo.")

    delta = Decimal(str(after.get("amount", "0"))) - Decimal(str(before.get("amount", "0")))
    if delta == 0:
        raise ValueError("No hay delta material de monto para crear ajuste compensatorio.")

    adjustment_type = tx.type
    if tx.type == Transaction.Type.EXPENSE and delta < 0:
        adjustment_type = Transaction.Type.INCOME
    elif tx.type == Transaction.Type.INCOME and delta < 0:
        adjustment_type = Transaction.Type.EXPENSE

    return create_manual_transaction(
        validated_data={
            "owner": tx.owner,
            "account": tx.account,
            "type": adjustment_type,
            "status": Transaction.Status.POSTED,
            "amount": abs(delta),
            "date": parse_date(str(after.get("date") or "")) or tx.date,
            "category": tx.category,
            "vendor": tx.vendor,
            "income_source": tx.income_source,
            "source": "reconciliation_adjustment",
            "provider": tx.provider,
            "confirmed": True,
            "affects_balance": True,
            "notes": f"Ajuste compensatorio por issue #{issue.pk} sobre transaccion #{tx.pk}.",
            "raw_payload": {
                "reconciliation_issue_id": str(issue.pk),
                "mode": "adjustment",
                "before": before,
                "after": after,
                "normalized": normalized,
            },
        },
        actor=None,
        event_source="finance.transactions.transaction_reconciliation_service.create_adjustment",
    )


def _build_replacement_pair(*, issue: TransactionReconciliationIssue, normalized: dict, actor=None) -> tuple[Transaction, Transaction]:
    original = issue.transaction
    target_account = _resolve_account(normalized)
    reversal = create_manual_transaction(
        validated_data={
            "owner": original.owner,
            "account": original.account,
            "type": _inverse_type(original.type),
            "status": Transaction.Status.POSTED,
            "amount": original.amount,
            "date": original.date,
            "category": original.category,
            "vendor": original.vendor,
            "income_source": original.income_source,
            "source": "reconciliation_reverse",
            "provider": original.provider,
            "confirmed": True,
            "affects_balance": True,
            "notes": f"Reverso compensatorio por replacement pair del issue #{issue.pk}.",
            "raw_payload": {
                "reconciliation_issue_id": str(issue.pk),
                "mode": "replacement_pair_reverse",
                "original_transaction_id": str(original.pk),
            },
        },
        actor=actor,
        event_source="finance.transactions.transaction_reconciliation_service.create_replacement_pair.reverse",
    )
    replacement = create_manual_transaction(
        validated_data={
            "owner": target_account.owner,
            "account": target_account,
            "type": normalized.get("type", original.type),
            "status": normalized.get("status", Transaction.Status.POSTED),
            "amount": Decimal(str(normalized.get("amount", original.amount))),
            "date": parse_date(str(normalized.get("date") or "")) or original.date,
            "source": "reconciliation_replacement",
            "provider": normalized.get("provider", original.provider),
            "external_id": normalized.get("external_id", original.external_id),
            "raw_payload": normalized.get("raw_payload") or {},
            "fingerprint": normalized.get("canonical_fingerprint", ""),
            "confirmed": bool(normalized.get("confirmed", True)),
            "affects_balance": bool(normalized.get("affects_balance", True)),
            "notes": normalized.get("notes") or f"Replacement pair del issue #{issue.pk} sobre transaccion #{original.pk}.",
        },
        actor=actor,
        event_source="finance.transactions.transaction_reconciliation_service.create_replacement_pair.replacement",
    )
    return reversal, replacement


def _build_reversal_transaction(*, issue: TransactionReconciliationIssue, normalized: dict):
    tx = issue.transaction
    return create_manual_transaction(
        validated_data={
            "owner": tx.owner,
            "account": tx.account,
            "type": _inverse_type(tx.type),
            "status": Transaction.Status.POSTED,
            "amount": tx.amount,
            "date": parse_date(str(normalized.get("date") or "")) or timezone.now().date(),
            "category": tx.category,
            "vendor": tx.vendor,
            "income_source": tx.income_source,
            "source": "reconciliation_reverse",
            "provider": tx.provider,
            "confirmed": True,
            "affects_balance": True,
            "notes": f"Reverso compensatorio por issue #{issue.pk} sobre transaccion #{tx.pk}.",
            "raw_payload": {
                "reconciliation_issue_id": str(issue.pk),
                "mode": "reverse",
                "normalized": normalized,
            },
        },
        actor=None,
        event_source="finance.transactions.transaction_reconciliation_service.create_reverse",
    )


@db_tx.atomic
def resolve_reconciliation_issue(
    *,
    issue: TransactionReconciliationIssue,
    action: str,
    actor=None,
    notes: str = "",
    payload: dict | None = None,
) -> TransactionReconciliationIssue:
    action = str(action or "").strip().lower()
    if issue.status != TransactionReconciliationIssue.Status.OPEN:
        already_closed_with_same_action = (
            issue.status == TransactionReconciliationIssue.Status.RESOLVED
            and issue.resolution_action == action
        ) or (
            issue.status == TransactionReconciliationIssue.Status.IGNORED
            and action == TransactionReconciliationIssue.ResolutionAction.IGNORE
        )
        if already_closed_with_same_action:
            return issue
        raise ValueError("El issue ya fue cerrado con otra accion.")

    normalized = _normalized_from_issue(issue)
    resolution_payload = {"input": payload or {}, "normalized": normalized}
    resolution_transaction = None
    original_tx = issue.transaction
    complex_replacement_needed = (
        str(normalized.get("account_id") or "") not in {"", str(original_tx.account_id)}
        or str(normalized.get("type") or original_tx.type) != str(original_tx.type)
        or str(normalized.get("provider") or original_tx.provider) != str(original_tx.provider)
    )

    if action == TransactionReconciliationIssue.ResolutionAction.IGNORE:
        issue.mark_ignored(actor=actor, notes=notes, payload=resolution_payload)
        _publish_issue_resolved(issue)
        return issue

    if action == TransactionReconciliationIssue.ResolutionAction.APPLY_PROVIDER_UPDATE:
        if complex_replacement_needed:
            raise ValueError(
                "Esta correccion cambia cuenta, tipo o proveedor. Usa create_adjustment para replacement pair formal."
            )
        account = _resolve_account(normalized)
        updated_tx = _update_transaction_from_intake(tx=issue.transaction, account=account, normalized=normalized)
        issue.transaction = updated_tx
        _sync_latest_provider_state(issue, normalized)
        issue.mark_resolved(action=action, actor=actor, notes=notes, payload=resolution_payload)
        _publish_issue_resolved(issue)
        return issue

    if action == TransactionReconciliationIssue.ResolutionAction.CREATE_ADJUSTMENT:
        if complex_replacement_needed:
            reversal_tx, replacement_tx = _build_replacement_pair(issue=issue, normalized=normalized, actor=actor)
            resolution_transaction = replacement_tx
            resolution_payload["replacement_pair"] = {
                "reversal_transaction_id": str(reversal_tx.pk),
                "replacement_transaction_id": str(replacement_tx.pk),
            }
            if issue.source_link_id and issue.source_link:
                _sync_source_link(source_link=issue.source_link, normalized=normalized, tx=replacement_tx)
            else:
                _ensure_source_link(tx=replacement_tx, normalized=normalized)
        else:
            resolution_transaction = _build_adjustment_transaction(issue=issue, normalized=normalized)
            _sync_latest_provider_state(issue, normalized)
        issue.mark_resolved(
            action=action,
            actor=actor,
            notes=notes,
            payload=resolution_payload,
            resolution_transaction=resolution_transaction,
        )
        _publish_issue_resolved(issue)
        return issue

    if action == TransactionReconciliationIssue.ResolutionAction.CREATE_REVERSAL:
        resolution_transaction = _build_reversal_transaction(issue=issue, normalized=normalized)
        _sync_latest_provider_state(issue, normalized)
        issue.mark_resolved(
            action=action,
            actor=actor,
            notes=notes,
            payload=resolution_payload,
            resolution_transaction=resolution_transaction,
        )
        _publish_issue_resolved(issue)
        return issue

    raise ValueError("Accion de reconciliacion no soportada.")
