from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db import transaction as db_tx
from django.utils import timezone
from django.utils.dateparse import parse_date

from finance.accounts.models.account import Account
from finance.transactions.Models import (
    Transaction,
    TransactionIntakeBatch,
    TransactionIntakeReceipt,
    TransactionReconciliationIssue,
    TransactionSourceLink,
)
from finance.transactions.domain_events import TransactionDomainEventTypes
from finance.transactions.event_service import publish_transaction_event_after_commit
from finance.transactions.transaction_state_service import is_transaction_countable_for_ledger


_REVERSE_PROVIDER_STATUSES = {"reversed", "reverse", "cancelled", "canceled", "voided"}
_MATERIAL_FIELDS = ("account_id", "amount", "date", "type", "status", "confirmed", "affects_balance")


@dataclass
class IntakeApplyResult:
    batch: TransactionIntakeBatch
    counts: Counter
    receipts: list[TransactionIntakeReceipt]

    @property
    def total(self) -> int:
        return int(sum(self.counts.values()))


def _canonical_decimal(value) -> str:
    return str(Decimal(str(value or "0")).quantize(Decimal("0.01")))


def _normalize_row_payload(*, provider: str, source: str, provider_account_id: str, row: dict) -> dict:
    raw_status = str(row.get("status") or Transaction.Status.POSTED).strip().lower()
    status = raw_status if raw_status in Transaction.Status.values else Transaction.Status.POSTED
    description = str(row.get("description") or row.get("notes") or "").strip()
    normalized = {
        "provider": str(provider or "").strip().lower(),
        "source": str(source or "").strip().lower(),
        "provider_account_id": str(provider_account_id or row.get("provider_account_id") or "").strip(),
        "account_id": row.get("account_id") or row.get("internal_account_id") or None,
        "external_id": str(row.get("external_id") or "").strip(),
        "provider_event_id": str(row.get("provider_event_id") or "").strip(),
        "provider_status": str(row.get("provider_status") or raw_status or "").strip().lower(),
        "type": str(row.get("type") or Transaction.Type.EXPENSE).strip().lower(),
        "status": status,
        "amount": _canonical_decimal(row.get("amount") or "0"),
        "date": str(parse_date(str(row.get("date") or "")) or row.get("date") or "").strip(),
        "currency": str(row.get("currency") or "").strip().upper(),
        "description": description,
        "notes": str(row.get("notes") or description).strip(),
        "confirmed": bool(row.get("confirmed", status in {Transaction.Status.POSTED, Transaction.Status.RECONCILED})),
        "affects_balance": bool(row.get("affects_balance", status not in {Transaction.Status.CANCELED, Transaction.Status.FAILED})),
        "raw_payload": row.get("raw_payload") or row.get("raw") or {},
        "metadata": row.get("metadata") or {},
    }
    if normalized["status"] == Transaction.Status.PENDING and normalized["confirmed"]:
        normalized["status"] = Transaction.Status.POSTED
    return normalized


def compute_canonical_fingerprint(normalized: dict) -> str:
    basis = {
        "provider": normalized.get("provider", ""),
        "source": normalized.get("source", ""),
        "provider_account_id": normalized.get("provider_account_id", ""),
        "amount": normalized.get("amount", ""),
        "currency": normalized.get("currency", ""),
        "date": normalized.get("date", ""),
        "type": normalized.get("type", ""),
        "external_id": normalized.get("external_id", ""),
        "provider_event_id": normalized.get("provider_event_id", ""),
        "description": normalized.get("description", "").strip().lower(),
    }
    raw = json.dumps(basis, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_account(normalized: dict) -> Account:
    account_id = normalized.get("account_id")
    provider = normalized.get("provider", "")
    provider_account_id = normalized.get("provider_account_id", "")
    if account_id:
        account = Account.objects.select_related("owner").filter(pk=account_id).first()
        if account:
            return account
    if provider and provider_account_id:
        account = (
            Account.objects.select_related("owner")
            .filter(provider__iexact=provider, external_id=provider_account_id)
            .first()
        )
        if account:
            return account
    raise ValueError("No se pudo resolver la cuenta interna para la fila de intake.")


def _find_existing_link(*, provider: str, source: str, provider_account_id: str, external_id: str, fingerprint: str):
    qs = TransactionSourceLink.objects.select_related("transaction")
    if external_id:
        link = qs.filter(
            provider__iexact=provider,
            source__iexact=source,
            provider_account_id=provider_account_id,
            external_id=external_id,
        ).first()
        if link:
            return link
    if fingerprint:
        return qs.filter(
            provider__iexact=provider,
            source__iexact=source,
            provider_account_id=provider_account_id,
            canonical_fingerprint=fingerprint,
        ).first()
    return None


def _find_legacy_transaction(*, account: Account, normalized: dict):
    provider = normalized.get("provider", "")
    external_id = normalized.get("external_id", "")
    fingerprint = normalized.get("canonical_fingerprint", "")
    qs = Transaction.objects.filter(owner=account.owner, account=account, provider__iexact=provider)
    if external_id:
        tx = qs.filter(external_id=external_id).first()
        if tx:
            return tx
    if fingerprint:
        return qs.filter(fingerprint=fingerprint).first()
    return None


def _transaction_material_state(tx: Transaction) -> dict:
    return {
        "account_id": str(tx.account_id or ""),
        "amount": _canonical_decimal(tx.amount),
        "date": str(tx.date),
        "type": tx.type,
        "status": tx.status,
        "confirmed": bool(tx.confirmed),
        "affects_balance": bool(tx.affects_balance),
    }


def _incoming_material_state(normalized: dict, account: Account) -> dict:
    return {
        "account_id": str(account.pk),
        "amount": normalized.get("amount", "0.00"),
        "date": normalized.get("date", ""),
        "type": normalized.get("type", Transaction.Type.EXPENSE),
        "status": normalized.get("status", Transaction.Status.POSTED),
        "confirmed": bool(normalized.get("confirmed", False)),
        "affects_balance": bool(normalized.get("affects_balance", True)),
    }


def _countable_state(material: dict) -> bool:
    return is_transaction_countable_for_ledger(material)


def _sync_source_link(*, source_link: TransactionSourceLink, normalized: dict, tx: Transaction) -> TransactionSourceLink:
    source_link.transaction = tx
    source_link.provider = normalized.get("provider", source_link.provider)
    source_link.source = normalized.get("source", source_link.source)
    source_link.provider_account_id = normalized.get("provider_account_id", source_link.provider_account_id)
    source_link.provider_status = normalized.get("provider_status", "")
    source_link.last_seen_at = timezone.now()
    source_link.last_normalized_payload = normalized
    source_link.canonical_fingerprint = normalized.get("canonical_fingerprint", "")
    if normalized.get("external_id"):
        source_link.external_id = normalized["external_id"]
    source_link.save(
        update_fields=[
            "transaction",
            "provider",
            "source",
            "provider_account_id",
            "provider_status",
            "last_seen_at",
            "last_normalized_payload",
            "canonical_fingerprint",
            "external_id",
            "updated_at",
        ]
    )
    return source_link


def _ensure_source_link(*, tx: Transaction, normalized: dict) -> TransactionSourceLink:
    link = _find_existing_link(
        provider=normalized.get("provider", ""),
        source=normalized.get("source", ""),
        provider_account_id=normalized.get("provider_account_id", ""),
        external_id=normalized.get("external_id", ""),
        fingerprint=normalized.get("canonical_fingerprint", ""),
    )
    if link is None:
        link = TransactionSourceLink.objects.create(
            transaction=tx,
            provider=normalized.get("provider", ""),
            source=normalized.get("source", ""),
            provider_account_id=normalized.get("provider_account_id", ""),
            external_id=normalized.get("external_id", ""),
            canonical_fingerprint=normalized.get("canonical_fingerprint", ""),
            provider_status=normalized.get("provider_status", ""),
            last_normalized_payload=normalized,
        )
        return link
    return _sync_source_link(source_link=link, normalized=normalized, tx=tx)


def _publish_intake_event(event_type: str, payload: dict, *, aggregate_type: str, aggregate_id: str | int, source: str) -> None:
    publish_transaction_event_after_commit(
        event_type=event_type,
        payload=payload,
        metadata={
            "context": "transactions",
            "source": source,
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
        },
    )


def _publish_batch_received(batch: TransactionIntakeBatch) -> None:
    _publish_intake_event(
        TransactionDomainEventTypes.TRANSACTION_INTAKE_BATCH_RECEIVED,
        {
            "batch_id": str(batch.pk),
            "owner_id": str(batch.owner_id or ""),
            "account_id": str(batch.account_id or ""),
            "provider": batch.provider,
            "source": batch.source,
            "provider_account_id": batch.provider_account_id,
            "row_count": batch.row_count,
            "request_id": batch.request_id,
        },
        aggregate_type="transaction_intake_batch",
        aggregate_id=batch.pk,
        source="finance.transactions.transaction_intake_service.receive_intake_batch",
    )


def _publish_batch_applied(batch: TransactionIntakeBatch, counts: Counter) -> None:
    _publish_intake_event(
        TransactionDomainEventTypes.TRANSACTION_INTAKE_BATCH_APPLIED,
        {
            "batch_id": str(batch.pk),
            "owner_id": str(batch.owner_id or ""),
            "account_id": str(batch.account_id or ""),
            "provider": batch.provider,
            "source": batch.source,
            "provider_account_id": batch.provider_account_id,
            "counts": dict(counts),
        },
        aggregate_type="transaction_intake_batch",
        aggregate_id=batch.pk,
        source="finance.transactions.transaction_intake_service.apply_intake_batch",
    )


def _publish_batch_failed(batch: TransactionIntakeBatch, error: str) -> None:
    _publish_intake_event(
        TransactionDomainEventTypes.TRANSACTION_INTAKE_BATCH_FAILED,
        {
            "batch_id": str(batch.pk),
            "provider": batch.provider,
            "source": batch.source,
            "provider_account_id": batch.provider_account_id,
            "error": (error or "")[:500],
        },
        aggregate_type="transaction_intake_batch",
        aggregate_id=batch.pk,
        source="finance.transactions.transaction_intake_service.apply_intake_batch",
    )


def _publish_duplicate_detected(receipt: TransactionIntakeReceipt) -> None:
    _publish_intake_event(
        TransactionDomainEventTypes.TRANSACTION_INTAKE_ROW_DUPLICATE_DETECTED,
        {
            "batch_id": str(receipt.batch_id),
            "receipt_id": str(receipt.pk),
            "transaction_id": str(receipt.materialized_transaction_id or ""),
            "provider": receipt.provider,
            "source": receipt.source,
            "provider_account_id": receipt.provider_account_id,
            "external_id": receipt.external_id,
            "canonical_fingerprint": receipt.canonical_fingerprint,
        },
        aggregate_type="transaction_intake_receipt",
        aggregate_id=receipt.pk,
        source="finance.transactions.transaction_intake_service._apply_receipt",
    )


def _publish_imported(receipt: TransactionIntakeReceipt, tx: Transaction) -> None:
    _publish_intake_event(
        TransactionDomainEventTypes.TRANSACTION_IMPORTED,
        {
            "batch_id": str(receipt.batch_id),
            "receipt_id": str(receipt.pk),
            "transaction_id": str(tx.pk),
            "owner_id": str(tx.owner_id),
            "account_id": str(tx.account_id),
            "provider": receipt.provider,
            "source": receipt.source,
            "provider_account_id": receipt.provider_account_id,
            "external_id": receipt.external_id,
        },
        aggregate_type="transaction",
        aggregate_id=tx.pk,
        source="finance.transactions.transaction_intake_service._apply_receipt.create",
    )


def _publish_reconciled(receipt: TransactionIntakeReceipt, tx: Transaction, *, action: str) -> None:
    _publish_intake_event(
        TransactionDomainEventTypes.TRANSACTION_RECONCILED,
        {
            "batch_id": str(receipt.batch_id),
            "receipt_id": str(receipt.pk),
            "transaction_id": str(tx.pk),
            "owner_id": str(tx.owner_id),
            "account_id": str(tx.account_id),
            "provider": receipt.provider,
            "source": receipt.source,
            "external_id": receipt.external_id,
            "action": action,
        },
        aggregate_type="transaction",
        aggregate_id=tx.pk,
        source="finance.transactions.transaction_intake_service._apply_receipt.reconcile",
    )


def _publish_corrected(receipt: TransactionIntakeReceipt, issue: TransactionReconciliationIssue, tx: Transaction) -> None:
    _publish_intake_event(
        TransactionDomainEventTypes.TRANSACTION_CORRECTED,
        {
            "batch_id": str(receipt.batch_id),
            "receipt_id": str(receipt.pk),
            "transaction_id": str(tx.pk),
            "issue_id": str(issue.pk),
            "issue_type": issue.issue_type,
            "provider": receipt.provider,
            "source": receipt.source,
            "external_id": receipt.external_id,
        },
        aggregate_type="transaction_reconciliation_issue",
        aggregate_id=issue.pk,
        source="finance.transactions.transaction_intake_service._apply_receipt.correct",
    )


def _publish_reversed(receipt: TransactionIntakeReceipt, tx: Transaction, *, issue: TransactionReconciliationIssue | None = None, action: str = "") -> None:
    _publish_intake_event(
        TransactionDomainEventTypes.TRANSACTION_REVERSED,
        {
            "batch_id": str(receipt.batch_id),
            "receipt_id": str(receipt.pk),
            "transaction_id": str(tx.pk),
            "issue_id": str(issue.pk) if issue else "",
            "provider": receipt.provider,
            "source": receipt.source,
            "external_id": receipt.external_id,
            "action": action,
        },
        aggregate_type="transaction",
        aggregate_id=tx.pk,
        source="finance.transactions.transaction_intake_service._apply_receipt.reverse",
    )


def _create_reconciliation_issue(*, tx: Transaction, source_link: TransactionSourceLink | None, issue_type: str, summary: str, details: dict) -> TransactionReconciliationIssue:
    return TransactionReconciliationIssue.objects.create(
        transaction=tx,
        source_link=source_link,
        issue_type=issue_type,
        summary=summary,
        details=details,
    )


def _create_transaction_from_intake(*, account: Account, normalized: dict) -> Transaction:
    return Transaction.objects.create(
        owner=account.owner,
        account=account,
        type=normalized.get("type", Transaction.Type.EXPENSE),
        status=normalized.get("status", Transaction.Status.POSTED),
        amount=Decimal(normalized.get("amount", "0.00")),
        date=parse_date(normalized.get("date", "")) or timezone.now().date(),
        source=normalized.get("source", "open_finance"),
        provider=normalized.get("provider", ""),
        external_id=normalized.get("external_id", ""),
        raw_payload=normalized.get("raw_payload") or {},
        fingerprint=normalized.get("canonical_fingerprint", ""),
        confirmed=bool(normalized.get("confirmed", False)),
        affects_balance=bool(normalized.get("affects_balance", True)),
        notes=normalized.get("notes", ""),
    )


def _update_transaction_from_intake(*, tx: Transaction, account: Account, normalized: dict) -> Transaction:
    tx.account = account
    tx.type = normalized.get("type", tx.type)
    tx.status = normalized.get("status", tx.status)
    tx.amount = Decimal(normalized.get("amount", tx.amount))
    tx.date = parse_date(normalized.get("date", "")) or tx.date
    tx.source = normalized.get("source", tx.source)
    tx.provider = normalized.get("provider", tx.provider)
    tx.external_id = normalized.get("external_id", tx.external_id)
    tx.raw_payload = normalized.get("raw_payload") or {}
    tx.fingerprint = normalized.get("canonical_fingerprint", tx.fingerprint)
    tx.confirmed = bool(normalized.get("confirmed", tx.confirmed))
    tx.affects_balance = bool(normalized.get("affects_balance", tx.affects_balance))
    tx.notes = normalized.get("notes", tx.notes)
    tx.save()
    return tx


def _apply_receipt(receipt: TransactionIntakeReceipt) -> str:
    normalized = dict(receipt.normalized_payload or {})
    account = _resolve_account(normalized)
    link = _find_existing_link(
        provider=receipt.provider,
        source=receipt.source,
        provider_account_id=receipt.provider_account_id,
        external_id=receipt.external_id,
        fingerprint=receipt.canonical_fingerprint,
    )
    tx = link.transaction if link else _find_legacy_transaction(account=account, normalized=normalized)
    if tx and link is None:
        link = _ensure_source_link(tx=tx, normalized=normalized)
    previous_receipt = (
        TransactionIntakeReceipt.objects.filter(
            provider=receipt.provider,
            source=receipt.source,
            provider_account_id=receipt.provider_account_id,
            materialized_transaction=tx,
        )
        .exclude(pk=receipt.pk)
        .order_by("-first_seen_at")
        .first()
        if tx
        else None
    )
    incoming_material = _incoming_material_state(normalized, account)
    provider_status = normalized.get("provider_status", "")

    if tx is None:
        tx = _create_transaction_from_intake(account=account, normalized=normalized)
        link = _ensure_source_link(tx=tx, normalized=normalized)
        receipt.status = TransactionIntakeReceipt.Status.MATERIALIZED
        receipt.materialized_transaction = tx
        receipt.last_error = ""
        receipt.last_seen_at = timezone.now()
        receipt.save(update_fields=["status", "materialized_transaction", "last_error", "last_seen_at", "updated_at"])
        _publish_imported(receipt, tx)
        return "materialized"

    current_material = _transaction_material_state(tx)
    same_material = all(str(current_material.get(field, "")) == str(incoming_material.get(field, "")) for field in _MATERIAL_FIELDS)
    previous_payload = (link.last_normalized_payload if link else {}) or {}
    payload_changed = previous_payload != normalized
    countable_now = _countable_state(current_material)

    if same_material and not payload_changed:
        receipt.status = TransactionIntakeReceipt.Status.DUPLICATE
        receipt.materialized_transaction = tx
        receipt.duplicate_of = previous_receipt
        receipt.last_error = ""
        receipt.last_seen_at = timezone.now()
        receipt.save(
            update_fields=[
                "status",
                "materialized_transaction",
                "duplicate_of",
                "last_error",
                "last_seen_at",
                "updated_at",
            ]
        )
        if link:
            _sync_source_link(source_link=link, normalized=normalized, tx=tx)
        _publish_duplicate_detected(receipt)
        return "duplicate"

    if provider_status in _REVERSE_PROVIDER_STATUSES or normalized.get("status") == Transaction.Status.CANCELED:
        if countable_now:
            issue = _create_reconciliation_issue(
                tx=tx,
                source_link=link,
                issue_type=TransactionReconciliationIssue.IssueType.REVERSE_REQUIRED,
                summary="La fuente externa reporta reverso o cancelacion sobre una transaccion ya contable.",
                details={"before": current_material, "after": incoming_material, "normalized": normalized},
            )
            receipt.status = TransactionIntakeReceipt.Status.REVERSED
            receipt.materialized_transaction = tx
            receipt.reconciliation_issue = issue
            receipt.last_error = ""
            receipt.last_seen_at = timezone.now()
            receipt.save(
                update_fields=[
                    "status",
                    "materialized_transaction",
                    "reconciliation_issue",
                    "last_error",
                    "last_seen_at",
                    "updated_at",
                ]
            )
            if link:
                _sync_source_link(source_link=link, normalized=normalized, tx=tx)
            _publish_reversed(receipt, tx, issue=issue, action="issue_created")
            return "reversed"
        tx.status = Transaction.Status.CANCELED
        tx.confirmed = False
        tx.affects_balance = False
        tx.raw_payload = normalized.get("raw_payload") or {}
        tx.save()
        if link:
            _sync_source_link(source_link=link, normalized=normalized, tx=tx)
        receipt.status = TransactionIntakeReceipt.Status.REVERSED
        receipt.materialized_transaction = tx
        receipt.last_error = ""
        receipt.last_seen_at = timezone.now()
        receipt.save(update_fields=["status", "materialized_transaction", "last_error", "last_seen_at", "updated_at"])
        _publish_reversed(receipt, tx, action="transaction_updated")
        return "reversed"

    material_fields_changed = [
        field for field in _MATERIAL_FIELDS if str(current_material.get(field, "")) != str(incoming_material.get(field, ""))
    ]
    if material_fields_changed and countable_now and any(field in {"account_id", "amount", "date", "type"} for field in material_fields_changed):
        issue = _create_reconciliation_issue(
            tx=tx,
            source_link=link,
            issue_type=TransactionReconciliationIssue.IssueType.CORRECTION_REQUIRED,
            summary="La fuente externa reporta un cambio material sobre una transaccion ya contable.",
            details={
                "before": current_material,
                "after": incoming_material,
                "changed_fields": material_fields_changed,
                "normalized": normalized,
            },
        )
        receipt.status = TransactionIntakeReceipt.Status.CORRECTED
        receipt.materialized_transaction = tx
        receipt.reconciliation_issue = issue
        receipt.last_error = ""
        receipt.last_seen_at = timezone.now()
        receipt.save(
            update_fields=[
                "status",
                "materialized_transaction",
                "reconciliation_issue",
                "last_error",
                "last_seen_at",
                "updated_at",
            ]
        )
        if link:
            _sync_source_link(source_link=link, normalized=normalized, tx=tx)
        _publish_corrected(receipt, issue, tx)
        return "corrected"

    if material_fields_changed:
        tx = _update_transaction_from_intake(tx=tx, account=account, normalized=normalized)
        if link:
            _sync_source_link(source_link=link, normalized=normalized, tx=tx)
        receipt.status = TransactionIntakeReceipt.Status.UPDATED
        receipt.materialized_transaction = tx
        receipt.last_error = ""
        receipt.last_seen_at = timezone.now()
        receipt.save(update_fields=["status", "materialized_transaction", "last_error", "last_seen_at", "updated_at"])
        _publish_reconciled(receipt, tx, action="transaction_updated")
        return "updated"

    if link:
        _sync_source_link(source_link=link, normalized=normalized, tx=tx)
    receipt.status = TransactionIntakeReceipt.Status.NOOP
    receipt.materialized_transaction = tx
    receipt.last_error = ""
    receipt.last_seen_at = timezone.now()
    receipt.save(update_fields=["status", "materialized_transaction", "last_error", "last_seen_at", "updated_at"])
    _publish_reconciled(receipt, tx, action="metadata_reconciled")
    return "noop"


@db_tx.atomic
def receive_intake_batch(
    *,
    provider: str,
    source: str,
    provider_account_id: str = "",
    cursor: str = "",
    request_id: str,
    idempotency_key: str,
    rows: Iterable[dict],
    raw_summary: dict | None = None,
) -> tuple[TransactionIntakeBatch, bool]:
    batch, created = TransactionIntakeBatch.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "provider": str(provider or "").strip().lower(),
            "source": str(source or "").strip().lower(),
            "provider_account_id": str(provider_account_id or "").strip(),
            "cursor": str(cursor or "").strip(),
            "request_id": str(request_id or "").strip(),
            "raw_summary": raw_summary or {},
        },
    )
    if not created:
        same_shape = (
            batch.provider == str(provider or "").strip().lower()
            and batch.source == str(source or "").strip().lower()
            and batch.provider_account_id == str(provider_account_id or "").strip()
        )
        if not same_shape:
            raise ValueError("El idempotency key ya existe para otro batch de intake.")
        return batch, False

    receipts = []
    resolved_owner = None
    resolved_account = None
    row_list = list(rows or [])
    for row in row_list:
        normalized = _normalize_row_payload(
            provider=batch.provider,
            source=batch.source,
            provider_account_id=batch.provider_account_id,
            row=row,
        )
        normalized["canonical_fingerprint"] = compute_canonical_fingerprint(normalized)
        account = _resolve_account(normalized)
        if resolved_account is None:
            resolved_account = account
            resolved_owner = account.owner
        elif resolved_account.pk != account.pk:
            raise ValueError("Un mismo batch de intake no debe mezclar cuentas internas distintas.")
        receipts.append(
            TransactionIntakeReceipt(
                batch=batch,
                provider=batch.provider,
                source=batch.source,
                provider_account_id=normalized.get("provider_account_id", ""),
                external_id=normalized.get("external_id", ""),
                provider_event_id=normalized.get("provider_event_id", ""),
                canonical_fingerprint=normalized.get("canonical_fingerprint", ""),
                normalized_payload=normalized,
                raw_payload=normalized.get("raw_payload") or {},
            )
        )
    if receipts:
        TransactionIntakeReceipt.objects.bulk_create(receipts)
    batch.owner = resolved_owner
    batch.account = resolved_account
    batch.row_count = len(receipts)
    batch.save(update_fields=["owner", "account", "row_count", "updated_at"])
    _publish_batch_received(batch)
    return batch, True


@db_tx.atomic
def apply_intake_batch(*, batch: TransactionIntakeBatch) -> IntakeApplyResult:
    batch.mark_processing()
    counts: Counter = Counter()
    processed_receipts: list[TransactionIntakeReceipt] = []
    try:
        receipts = list(
            batch.receipts.select_related("materialized_transaction", "reconciliation_issue")
            .filter(status__in=[TransactionIntakeReceipt.Status.RECEIVED, TransactionIntakeReceipt.Status.FAILED])
            .order_by("first_seen_at")
        )
        for receipt in receipts:
            result = _apply_receipt(receipt)
            counts[result] += 1
            processed_receipts.append(receipt)
        partial = counts.get("failed", 0) > 0 or counts.get("corrected", 0) > 0 or counts.get("reversed", 0) > 0
        batch.mark_applied(partial=partial)
        _publish_batch_applied(batch, counts)
        return IntakeApplyResult(batch=batch, counts=counts, receipts=processed_receipts)
    except Exception as exc:
        batch.mark_failed(str(exc))
        _publish_batch_failed(batch, str(exc))
        raise


def receive_single_intake_row(
    *,
    provider: str,
    source: str,
    provider_account_id: str = "",
    request_id: str,
    idempotency_key: str,
    row: dict,
) -> IntakeApplyResult:
    batch, _created = receive_intake_batch(
        provider=provider,
        source=source,
        provider_account_id=provider_account_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        rows=[row],
        raw_summary={"mode": "single_row"},
    )
    return apply_intake_batch(batch=batch)


def reconcile_intake_batch(
    *,
    provider: str,
    source: str,
    provider_account_id: str = "",
    request_id: str,
    idempotency_key: str,
    rows: Iterable[dict],
    cursor: str = "",
) -> IntakeApplyResult:
    batch, _created = receive_intake_batch(
        provider=provider,
        source=source,
        provider_account_id=provider_account_id,
        cursor=cursor,
        request_id=request_id,
        idempotency_key=idempotency_key,
        rows=rows,
        raw_summary={"mode": "reconcile"},
    )
    return apply_intake_batch(batch=batch)
