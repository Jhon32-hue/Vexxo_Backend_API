from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from identity.consents.models import ConsentStatus
from security.validators import sanitize_external_payload, validate_external_payload

from integrations.open_banking.adapters import OpenBankingProviderError, get_open_banking_adapter
from integrations.open_banking.contracts import mapper_version
from integrations.open_banking.models import (
    OpenBankingConnection,
    OpenBankingExternalPayload,
    OpenBankingReconciliationIssue,
    OpenBankingSyncRun,
    OpenBankingTimelineEvent,
)


REAUTHORIZATION_ERROR_CODES = {
    "authorization_pending",
    "invalid_credentials",
    "consent_expired",
    "belvo_http_401",
    "belvo_http_403",
    "salt_edge_http_401",
    "salt_edge_http_403",
}


def record_timeline(
    *,
    connection: OpenBankingConnection,
    event_type: str,
    source: str,
    status: str = "",
    provider_event_id: str = "",
    occurred_at=None,
    metadata: dict | None = None,
) -> OpenBankingTimelineEvent:
    return OpenBankingTimelineEvent.objects.create(
        connection=connection,
        event_type=event_type[:96],
        source=source[:64],
        status=status[:32],
        provider_event_id=provider_event_id[:160],
        occurred_at=occurred_at or timezone.now(),
        safe_metadata=sanitize_external_payload(metadata or {}),
    )


def quarantine_external_payload(
    *,
    connection: OpenBankingConnection,
    resource_type: str,
    payload,
    account_link=None,
    cursor_in: str = "",
    cursor_out: str = "",
    schema_version: str = "open_banking.canonical.v1",
    provenance: str = "",
) -> tuple[OpenBankingExternalPayload, bool]:
    serializable = json.loads(json.dumps(payload, ensure_ascii=True, default=str))
    validate_external_payload(serializable)
    sanitized = sanitize_external_payload(serializable)
    encoded = json.dumps(sanitized, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_hash = hashlib.sha256(encoded).hexdigest()
    ttl_days = max(1, int(getattr(settings, "OPEN_BANKING_EXTERNAL_PAYLOAD_TTL_DAYS", 30)))
    record, created = OpenBankingExternalPayload.objects.get_or_create(
        connection=connection,
        resource_type=resource_type,
        payload_sha256=payload_hash,
        defaults={
            "account_link": account_link,
            "provider": connection.provider,
            "schema_version": schema_version[:64],
            "mapper_version": mapper_version(connection.provider)[:64],
            "classification": "restricted",
            "provenance": (provenance or f"{connection.provider}.{resource_type}")[:160],
            "cursor_in": cursor_in[:255],
            "cursor_out": cursor_out[:255],
            "sanitized_payload": sanitized,
            "safe_metadata": {"item_count": len(payload) if isinstance(payload, list) else 1},
            "expires_at": timezone.now() + timedelta(days=ttl_days),
        },
    )
    return record, created


def mark_payload_normalized(payload: OpenBankingExternalPayload) -> None:
    payload.status = OpenBankingExternalPayload.Status.NORMALIZED
    payload.attempt_count += 1
    payload.normalized_at = timezone.now()
    payload.last_error = ""
    payload.save(update_fields=["status", "attempt_count", "normalized_at", "last_error", "updated_at"])


def mark_payload_failed(payload: OpenBankingExternalPayload, error: Exception) -> None:
    payload.attempt_count += 1
    max_attempts = max(1, int(getattr(settings, "OPEN_BANKING_PAYLOAD_MAX_ATTEMPTS", 5)))
    payload.status = (
        OpenBankingExternalPayload.Status.DEAD
        if payload.attempt_count >= max_attempts
        else OpenBankingExternalPayload.Status.REJECTED
    )
    payload.last_error = str(error)[:2000]
    payload.save(update_fields=["status", "attempt_count", "last_error", "updated_at"])


def mark_sync_retry(sync_run: OpenBankingSyncRun, error: OpenBankingProviderError) -> OpenBankingSyncRun:
    sync_run.attempt_count += 1
    if error.code in REAUTHORIZATION_ERROR_CODES:
        sync_run.status = OpenBankingSyncRun.Status.REAUTHORIZATION
        sync_run.next_attempt_at = None
        connection = sync_run.connection
        connection.status = OpenBankingConnection.Status.ATTENTION_REQUIRED
        connection.reauthorization_required_at = timezone.now()
        connection.error_code = error.code[:64]
        connection.error_message = "La conexion bancaria requiere autorizacion del usuario."
        connection.save(
            update_fields=[
                "status",
                "reauthorization_required_at",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
    elif sync_run.attempt_count >= sync_run.max_attempts:
        sync_run.status = OpenBankingSyncRun.Status.DEAD
        sync_run.next_attempt_at = None
    else:
        sync_run.status = OpenBankingSyncRun.Status.RETRY
        base = max(1, int(getattr(settings, "OPEN_BANKING_RETRY_BASE_SECONDS", 30)))
        maximum = max(base, int(getattr(settings, "OPEN_BANKING_RETRY_MAX_SECONDS", 3600)))
        delay = min(maximum, base * (2 ** (sync_run.attempt_count - 1)))
        sync_run.next_attempt_at = timezone.now() + timedelta(seconds=delay)
    sync_run.error_code = error.code[:64]
    sync_run.last_error = str(error)[:2000]
    sync_run.save(
        update_fields=[
            "status",
            "attempt_count",
            "next_attempt_at",
            "error_code",
            "last_error",
            "updated_at",
        ]
    )
    record_timeline(
        connection=sync_run.connection,
        event_type="sync.retry_scheduled" if sync_run.status == OpenBankingSyncRun.Status.RETRY else f"sync.{sync_run.status}",
        source="integrations.open_banking.lifecycle",
        status=sync_run.status,
        metadata={"error_code": error.code, "attempt_count": sync_run.attempt_count},
    )
    return sync_run


@transaction.atomic
def refresh_connection_credentials(connection: OpenBankingConnection) -> OpenBankingConnection:
    connection = OpenBankingConnection.objects.select_for_update().select_related("consent").get(pk=connection.pk)
    if connection.consent.status != ConsentStatus.GRANTED or (
        connection.consent.expires_at and connection.consent.expires_at <= timezone.now()
    ):
        raise OpenBankingProviderError("El consentimiento expiro.", code="consent_expired")
    get_open_banking_adapter(connection.provider).refresh_credentials(connection=connection)
    connection.credential_expires_at = timezone.now() + timedelta(days=90)
    connection.reauthorization_required_at = None
    connection.error_code = ""
    connection.error_message = ""
    connection.save(
        update_fields=[
            "credential_expires_at",
            "reauthorization_required_at",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    record_timeline(
        connection=connection,
        event_type="credentials.refreshed",
        source="integrations.open_banking.lifecycle",
        status=connection.status,
    )
    return connection


def expire_open_banking_consents(*, now=None, limit: int = 500) -> dict:
    now = now or timezone.now()
    queryset = (
        OpenBankingConnection.objects.select_related("consent")
        .filter(consent__status=ConsentStatus.GRANTED, consent__expires_at__isnull=False, consent__expires_at__lte=now)
        .exclude(status=OpenBankingConnection.Status.REVOKED)
        .order_by("consent__expires_at")[: max(1, min(int(limit), 5000))]
    )
    expired = 0
    for connection in queryset:
        with transaction.atomic():
            consent = connection.consent
            consent.mark_expired(commit=True)
            connection.status = OpenBankingConnection.Status.ATTENTION_REQUIRED
            connection.reauthorization_required_at = now
            connection.next_sync_at = None
            connection.error_code = "consent_expired"
            connection.error_message = "El consentimiento Open Banking expiro."
            connection.save(
                update_fields=[
                    "status",
                    "reauthorization_required_at",
                    "next_sync_at",
                    "error_code",
                    "error_message",
                    "updated_at",
                ]
            )
            connection.account_links.filter(is_active=True).update(is_active=False, updated_at=now)
            record_timeline(
                connection=connection,
                event_type="consent.expired",
                source="integrations.open_banking.lifecycle",
                status=connection.status,
            )
            expired += 1
    return {"expired_connections": expired}


def purge_external_payloads(*, now=None, limit: int = 500) -> dict:
    now = now or timezone.now()
    records = list(
        OpenBankingExternalPayload.objects.filter(expires_at__lte=now)
        .exclude(status=OpenBankingExternalPayload.Status.PURGED)
        .order_by("expires_at")[: max(1, min(int(limit), 5000))]
    )
    for record in records:
        record.sanitized_payload = {}
        record.status = OpenBankingExternalPayload.Status.PURGED
        record.last_error = ""
        record.updated_at = now
    if records:
        OpenBankingExternalPayload.objects.bulk_update(
            records,
            ["sanitized_payload", "status", "last_error", "updated_at"],
        )
    return {"purged_payloads": len(records)}


def retry_due_open_banking_syncs(*, now=None, limit: int = 100) -> dict:
    from finance.accounts.services.account_sync_service import schedule_account_sync

    now = now or timezone.now()
    runs = list(
        OpenBankingSyncRun.objects.select_related("account_link__account")
        .filter(status=OpenBankingSyncRun.Status.RETRY, next_attempt_at__lte=now)
        .order_by("next_attempt_at")[: max(1, min(int(limit), 1000))]
    )
    scheduled = 0
    for sync_run in runs:
        source_run_id = sync_run.idempotency_key.rsplit(":", 1)[-1]
        schedule_account_sync(
            account=sync_run.account_link.account,
            data={"run_at": now, "sync_run_id": source_run_id},
            metadata={"source": "integrations.open_banking.retry", "retry_attempt": sync_run.attempt_count},
        )
        sync_run.status = OpenBankingSyncRun.Status.PENDING
        sync_run.next_attempt_at = None
        sync_run.save(update_fields=["status", "next_attempt_at", "updated_at"])
        scheduled += 1
    return {"scheduled_retries": scheduled}


def reconcile_connection_account(*, account_link, tolerance: Decimal | None = None):
    snapshot = get_open_banking_adapter(account_link.connection.provider).reconcile(
        connection=account_link.connection,
        external_account_id=account_link.external_account_id,
    )
    if snapshot.current_balance is None:
        return {"status": "provider_balance_unavailable", "issue_id": None}
    default_tolerance = Decimal("1.00") if snapshot.currency == "COP" else Decimal("0.01")
    effective_tolerance = abs(Decimal(tolerance if tolerance is not None else default_tolerance))
    ledger_balance = Decimal(account_link.account.current_balance()).quantize(Decimal("0.01"))
    difference = (snapshot.current_balance - ledger_balance).quantize(Decimal("0.01"))
    if abs(difference) <= effective_tolerance:
        record_timeline(
            connection=account_link.connection,
            event_type="reconciliation.matched",
            source="integrations.open_banking.lifecycle",
            status="matched",
            metadata={"account_link_id": account_link.pk, "currency": snapshot.currency},
        )
        return {"status": "matched", "issue_id": None, "difference": str(difference)}
    issue = OpenBankingReconciliationIssue.objects.filter(
        account_link=account_link,
        status=OpenBankingReconciliationIssue.Status.OPEN,
        provider_balance=snapshot.current_balance,
        ledger_balance=ledger_balance,
        difference=difference,
        tolerance=effective_tolerance,
    ).first()
    if issue is None:
        issue = OpenBankingReconciliationIssue.objects.create(
            connection=account_link.connection,
            account_link=account_link,
            currency=snapshot.currency,
            provider_balance=snapshot.current_balance,
            ledger_balance=ledger_balance,
            difference=difference,
            tolerance=effective_tolerance,
            provider_as_of=snapshot.as_of,
            safe_metadata={"schema_version": snapshot.schema_version, "provider": snapshot.provider},
        )
    record_timeline(
        connection=account_link.connection,
        event_type="reconciliation.difference_detected",
        source="integrations.open_banking.lifecycle",
        status="open",
        metadata={"account_link_id": account_link.pk, "issue_id": issue.pk, "currency": snapshot.currency},
    )
    return {"status": "difference", "issue_id": issue.pk, "difference": str(difference)}
