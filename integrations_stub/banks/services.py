"""
Servicios internos stub para sincronizacion bancaria.

Descripcion general:
- procesa jobs internos de sync disparados por Cloud Tasks o por operadores
- actualiza el estado de sync de cuentas y publica eventos coherentes

Analisis detallado:
- esta capa existe como receptor temporal dentro del monolito mientras el
  `integrations_service` externo todavia no esta separado
- delega el lifecycle real del sync al servicio canonico de `accounts` para no
  duplicar reglas ni idempotencia
"""

from __future__ import annotations

from django.db import transaction

from finance.accounts.models import Account
from finance.accounts.services.account_sync_service import (
    mark_account_sync_error,
    mark_account_sync_running,
    mark_account_sync_stale,
    mark_account_sync_success,
)
from finance.accounts.services.intelligence_service import refresh_account_intelligence_for_user
from finance.accounts.services.user_integration_service import revoke_provider_integration_access_for_user
from integrations.open_banking.local_mock import build_local_mock_snapshot, record_local_mock_sync
from integrations_stub.banks.transaction_bridge import process_stub_transactions_sync_batch


@transaction.atomic
def process_stub_account_sync(
    *,
    account: Account,
    event: dict | None = None,
    mode: str = "success",
    sync_cursor: str = "",
    next_sync_at=None,
    duration_ms: int = 0,
    provider_metadata: dict | None = None,
    message: str = "",
    retry_in_minutes: int | None = None,
) -> Account:
    upstream_event = dict(event or {})
    upstream_payload = dict(upstream_event.get("payload") or {})
    upstream_metadata = {
        "source": "integrations_stub.banks.process_stub_account_sync",
        "trigger_event_type": upstream_event.get("type", ""),
        "correlation_id": upstream_event.get("correlation_id"),
        "causation_id": upstream_event.get("id"),
        "request_id": upstream_event.get("request_id"),
        "sync_run_id": upstream_payload.get("sync_run_id") or upstream_event.get("sync_run_id"),
    }

    if not account.has_external_link:
        raise ValueError("La cuenta no esta vinculada a un proveedor externo.")

    mark_account_sync_running(
        account=account,
        data={
            "sync_cursor": sync_cursor,
            "next_sync_at": next_sync_at,
            "sync_run_id": upstream_payload.get("sync_run_id") or upstream_event.get("sync_run_id"),
        },
        metadata=upstream_metadata,
    )

    if mode == "success":
        effective_cursor = sync_cursor
        effective_provider_metadata = dict(provider_metadata or {})
        local_mock_result = None
        if account.provider == "local_mock":
            snapshot = build_local_mock_snapshot(account=account)
            sync_run_id = str(upstream_metadata.get("sync_run_id") or "manual")[:64]
            local_mock_result = process_stub_transactions_sync_batch(
                provider=snapshot["provider"],
                source=snapshot["source"],
                provider_account_id=snapshot["provider_account_id"],
                request_id=f"local-mock-{account.pk}-{sync_run_id}"[:64],
                idempotency_key=f"local-mock-sync:{account.pk}:{sync_run_id}:{snapshot['fixture_version']}",
                rows=snapshot["rows"],
                cursor=snapshot["cursor"],
                raw_summary={
                    "mode": "local_mock_fixture",
                    "fixture_version": snapshot["fixture_version"],
                    "row_count": len(snapshot["rows"]),
                },
            )
            effective_cursor = snapshot["cursor"]
            effective_provider_metadata.update(
                {
                    "local_mock_fixture_version": snapshot["fixture_version"],
                    "last_intake_batch_id": local_mock_result["batch_id"],
                    "last_intake_counts": local_mock_result["counts"],
                }
            )
        mark_account_sync_success(
            account=account,
            data={
                "sync_cursor": effective_cursor,
                "next_sync_at": next_sync_at,
                "duration_ms": duration_ms,
                "provider_metadata": effective_provider_metadata,
                "sync_run_id": upstream_payload.get("sync_run_id") or upstream_event.get("sync_run_id"),
            },
            metadata=upstream_metadata,
        )
        if local_mock_result is not None:
            record_local_mock_sync(
                account=account,
                cursor=effective_cursor,
                intake_result=local_mock_result,
                next_sync_at=next_sync_at,
            )
        return account

    if mode == "stale":
        mark_account_sync_stale(account, metadata=upstream_metadata)
        return account

    mark_account_sync_error(
        account=account,
        data={
            "message": message or "sync_failed",
            "next_sync_at": next_sync_at,
            "retry_in_minutes": retry_in_minutes,
            "sync_run_id": upstream_payload.get("sync_run_id") or upstream_event.get("sync_run_id"),
        },
        metadata=upstream_metadata,
    )
    return account


def process_stub_account_intelligence_refresh(*, owner_id: str | int, event: dict | None = None) -> dict:
    upstream_event = dict(event or {})
    result = refresh_account_intelligence_for_user(owner_id)
    if result is None:
        raise ValueError("No se encontro el usuario para refrescar inteligencia de accounts.")

    return {
        "owner_id": str(owner_id),
        "trigger_event_type": upstream_event.get("type", ""),
        "portfolio_snapshot_id": str(result["portfolio_snapshot"].pk),
        "risk_snapshot_id": str(result["risk_snapshot"].pk),
        "product_signals_count": len(result["product_signals"]),
    }


def process_stub_consent_revocation(*, user_id: str | int, provider: str = "", consent_type: str = "", event: dict | None = None) -> dict:
    from django.contrib.auth import get_user_model

    upstream_event = dict(event or {})
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        raise ValueError("No se encontro el usuario para revocar integraciones.")

    from integrations.open_banking.services import teardown_open_banking_connections_for_consent_revocation

    open_banking_result = teardown_open_banking_connections_for_consent_revocation(
        user=user,
        provider=provider,
        reason=consent_type or "consent_revoked",
    )
    result = revoke_provider_integration_access_for_user(
        user=user,
        provider=provider,
        legal_reason=consent_type or "consent_revoked",
    )
    result["trigger_event_type"] = upstream_event.get("type", "")
    result["consent_type"] = consent_type
    result.update(open_banking_result)
    return result
