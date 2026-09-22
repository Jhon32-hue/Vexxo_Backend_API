from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from finance.accounts.services.account_sync_service import (
    mark_account_sync_error,
    mark_account_sync_running,
    mark_account_sync_success,
)
from identity.consents.models import ConsentStatus
from integrations.open_banking.adapters import OpenBankingProviderError, get_open_banking_adapter
from integrations.open_banking.lifecycle import (
    mark_payload_failed,
    mark_payload_normalized,
    mark_sync_retry,
    quarantine_external_payload,
    reconcile_connection_account,
    record_timeline,
)
from integrations.open_banking.models import (
    OpenBankingAccountLink,
    OpenBankingConnection,
    OpenBankingExternalPayload,
    OpenBankingSyncRun,
)
from integrations_stub.banks.transaction_bridge import process_stub_transactions_sync_batch


def process_open_banking_account_sync(*, account, event: dict | None = None):
    link = OpenBankingAccountLink.objects.select_related("connection__consent", "account").get(
        account=account,
        is_active=True,
    )
    connection = link.connection
    payload = dict((event or {}).get("payload") or {})
    sync_run_id = str(payload.get("sync_run_id") or "manual")[:64]
    metadata = {"source": "integrations.open_banking.sync", "sync_run_id": sync_run_id}
    _assert_connection_can_sync(connection)
    sync_run, created = OpenBankingSyncRun.objects.get_or_create(
        idempotency_key=f"open-banking-sync:{account.pk}:{sync_run_id}",
        defaults={
            "connection": connection,
            "account_link": link,
            "cursor_in": link.sync_cursor,
            "max_attempts": max(1, int(getattr(settings, "OPEN_BANKING_SYNC_MAX_ATTEMPTS", 5))),
        },
    )
    if not created and sync_run.status == OpenBankingSyncRun.Status.SUCCEEDED:
        return account

    sync_run.status = OpenBankingSyncRun.Status.RUNNING
    sync_run.started_at = sync_run.started_at or timezone.now()
    sync_run.next_attempt_at = None
    sync_run.save(update_fields=["status", "started_at", "next_attempt_at", "updated_at"])
    mark_account_sync_running(account=account, data={"sync_run_id": sync_run_id}, metadata=metadata)
    adapter = get_open_banking_adapter(connection.provider)
    cursor = link.sync_cursor
    total_items = 0
    total_pages = 0
    last_intake: dict = {"batch_id": "", "counts": {}, "total": 0}
    max_pages = max(1, min(int(getattr(settings, "OPEN_BANKING_SYNC_MAX_PAGES", 100)), 500))

    try:
        for page_number in range(1, max_pages + 1):
            page = adapter.fetch_transactions_page(
                connection=connection,
                external_account_id=link.external_account_id,
                cursor=cursor,
            )
            quarantine, _ = quarantine_external_payload(
                connection=connection,
                account_link=link,
                resource_type=OpenBankingExternalPayload.ResourceType.TRANSACTIONS,
                payload=page.items,
                cursor_in=cursor,
                cursor_out=page.next_cursor,
                schema_version=page.schema_version,
                provenance=f"{connection.provider}.transactions.page",
            )
            try:
                rows = [adapter.normalize_transaction(row) for row in page.items]
                if rows:
                    last_intake = process_stub_transactions_sync_batch(
                        provider=connection.provider,
                        source="open_banking",
                        provider_account_id=link.external_account_id,
                        request_id=f"open-banking-{account.pk}-{sync_run_id}-{page_number}"[:64],
                        idempotency_key=f"open-banking-page:{quarantine.pk}",
                        rows=rows,
                        cursor=page.next_cursor or cursor,
                        raw_summary={
                            "adapter": connection.provider,
                            "row_count": len(rows),
                            "schema_version": page.schema_version,
                            "mapper_version": quarantine.mapper_version,
                            "quarantine_id": quarantine.pk,
                        },
                    )
                mark_payload_normalized(quarantine)
            except Exception as exc:
                mark_payload_failed(quarantine, exc)
                raise
            total_pages += 1
            total_items += len(page.items)
            cursor = page.next_cursor or cursor
            sync_run.page_count = total_pages
            sync_run.item_count = total_items
            sync_run.cursor_out = cursor
            sync_run.save(update_fields=["page_count", "item_count", "cursor_out", "updated_at"])
            if not page.has_more or not page.next_cursor:
                break
        else:
            raise OpenBankingProviderError("La paginacion excedio el limite operativo.", code="pagination_limit")

        reconciliation = reconcile_connection_account(account_link=link)
    except OpenBankingProviderError as exc:
        mark_sync_retry(sync_run, exc)
        mark_account_sync_error(
            account=account,
            data={"sync_run_id": sync_run_id, "message": str(exc)},
            metadata={**metadata, "error_code": exc.code},
        )
        raise
    except Exception as exc:
        provider_error = OpenBankingProviderError(str(exc), code="normalization_or_intake_error")
        mark_sync_retry(sync_run, provider_error)
        mark_account_sync_error(
            account=account,
            data={"sync_run_id": sync_run_id, "message": str(exc)},
            metadata={**metadata, "error_code": provider_error.code},
        )
        raise

    next_sync_at = timezone.now() + timedelta(minutes=30)
    with transaction.atomic():
        locked_link = OpenBankingAccountLink.objects.select_for_update().select_related("connection").get(pk=link.pk)
        locked_link.sync_cursor = cursor
        locked_link.save(update_fields=["sync_cursor", "updated_at"])
        locked_connection = locked_link.connection
        locked_connection.status = OpenBankingConnection.Status.CONNECTED
        locked_connection.last_synced_at = timezone.now()
        locked_connection.next_sync_at = next_sync_at
        locked_connection.error_code = ""
        locked_connection.error_message = ""
        locked_connection.save(
            update_fields=[
                "status", "last_synced_at", "next_sync_at", "error_code", "error_message", "updated_at",
            ]
        )
        sync_run.status = OpenBankingSyncRun.Status.SUCCEEDED
        sync_run.cursor_out = cursor
        sync_run.page_count = total_pages
        sync_run.item_count = total_items
        sync_run.error_code = ""
        sync_run.last_error = ""
        sync_run.completed_at = timezone.now()
        sync_run.safe_metadata = {
            "last_intake_batch_id": last_intake.get("batch_id", ""),
            "reconciliation_status": reconciliation.get("status", ""),
        }
        sync_run.save(
            update_fields=[
                "status", "cursor_out", "page_count", "item_count", "error_code", "last_error",
                "completed_at", "safe_metadata", "updated_at",
            ]
        )
    mark_account_sync_success(
        account=account,
        data={
            "sync_cursor": cursor,
            "next_sync_at": next_sync_at,
            "provider_metadata": {
                "last_intake_batch_id": last_intake.get("batch_id", ""),
                "last_intake_counts": last_intake.get("counts", {}),
                "last_page_count": total_pages,
                "last_item_count": total_items,
                "reconciliation": reconciliation,
            },
            "sync_run_id": sync_run_id,
        },
        metadata=metadata,
    )
    record_timeline(
        connection=connection,
        event_type="sync.completed",
        source="integrations.open_banking.sync",
        status="succeeded",
        metadata={"page_count": total_pages, "item_count": total_items, "sync_run_id": sync_run_id},
    )
    return account


def _assert_connection_can_sync(connection: OpenBankingConnection) -> None:
    now = timezone.now()
    if connection.status == OpenBankingConnection.Status.REVOKED:
        raise OpenBankingProviderError("La conexion fue revocada.", code="connection_revoked")
    if connection.consent.status != ConsentStatus.GRANTED:
        raise OpenBankingProviderError("El consentimiento no esta activo.", code="consent_expired")
    if connection.consent.expires_at and connection.consent.expires_at <= now:
        raise OpenBankingProviderError("El consentimiento expiro.", code="consent_expired")
    if connection.credential_expires_at and connection.credential_expires_at <= now:
        raise OpenBankingProviderError("La credencial expiro.", code="invalid_credentials")
