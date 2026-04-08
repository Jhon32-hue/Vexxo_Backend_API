from __future__ import annotations

from finance.transactions.Models import TransactionReconciliationIssue
from finance.transactions.transaction_intake_service import apply_intake_batch, receive_intake_batch
from finance.transactions.transaction_reconciliation_service import resolve_reconciliation_issue


def process_stub_transactions_sync_batch(
    *,
    provider: str,
    source: str,
    provider_account_id: str = "",
    request_id: str,
    idempotency_key: str,
    rows: list[dict],
    cursor: str = "",
    raw_summary: dict | None = None,
) -> dict:
    batch, created = receive_intake_batch(
        provider=provider,
        source=source,
        provider_account_id=provider_account_id,
        cursor=cursor,
        request_id=request_id,
        idempotency_key=idempotency_key,
        rows=rows,
        raw_summary=raw_summary or {"mode": "stub_bank_sync"},
    )
    result = apply_intake_batch(batch=batch)
    return {
        "created": created,
        "batch_id": str(batch.pk),
        "status": batch.status,
        "counts": dict(result.counts),
        "total": result.total,
    }


def process_stub_transactions_reconciliation_resolution(
    *,
    issue_id: int,
    action: str,
    notes: str = "",
    payload: dict | None = None,
) -> dict:
    issue = TransactionReconciliationIssue.objects.select_related("transaction", "source_link").filter(pk=issue_id).first()
    if issue is None:
        raise ValueError("Issue de reconciliacion no encontrado.")
    issue = resolve_reconciliation_issue(
        issue=issue,
        action=action,
        actor=None,
        notes=notes,
        payload=payload or {},
    )
    return {
        "issue_id": str(issue.pk),
        "status": issue.status,
        "resolution_action": issue.resolution_action,
        "resolution_transaction_id": str(issue.resolution_transaction_id or ""),
    }
