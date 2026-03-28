"""
Servicios internos stub para sincronizacion bancaria.

Descripcion general:
- procesa jobs internos de sync disparados por Cloud Tasks o por operadores
- actualiza el estado de sync de cuentas y publica eventos coherentes

Analisis detallado:
- esta capa existe como receptor temporal dentro del monolito mientras el
  `integrations_service` externo todavia no esta separado
- el objetivo es mantener el contrato del sistema listo: una task llega, se
  procesa, la cuenta cambia de estado y el dominio emite eventos
"""

from __future__ import annotations

from django.db import transaction

from finance.accounts.domain.events import AccountDomainEventTypes, build_account_sync_payload
from finance.accounts.models import Account
from finance.accounts.services import publish_account_event, publish_account_sync_event
from finance.accounts.services import revoke_provider_integration_access_for_user
from finance.accounts.services.intelligence_service import refresh_account_intelligence_for_user


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
    upstream_metadata = {
        "source": "integrations_stub.banks.process_stub_account_sync",
        "trigger_event_type": upstream_event.get("type", ""),
        "correlation_id": upstream_event.get("correlation_id"),
        "causation_id": upstream_event.get("id"),
    }

    if not account.has_external_link:
        raise ValueError("La cuenta no esta vinculada a un proveedor externo.")

    if sync_cursor:
        account.sync_cursor = sync_cursor
    if next_sync_at is not None:
        account.next_sync_at = next_sync_at

    account.mark_sync_running(commit=False)
    account.save(update_fields=["sync_cursor", "next_sync_at", "sync_status", "last_sync_status_at", "updated_at"])
    publish_account_sync_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
        change="mark_sync_running",
        extra={"sync_cursor": account.sync_cursor},
        metadata=upstream_metadata,
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STARTED,
        payload=build_account_sync_payload(
            account=account,
            change="sync_started",
            extra={"sync_cursor": account.sync_cursor},
        ),
        metadata=upstream_metadata,
    )

    if mode == "success":
        if provider_metadata:
            merged = dict(account.provider_metadata or {})
            merged.update(provider_metadata)
            account.provider_metadata = merged
        account.mark_sync_ok(commit=False, duration_ms=duration_ms)
        account.save(
            update_fields=[
                "sync_status",
                "sync_error_message",
                "last_sync_at",
                "last_sync_status_at",
                "sync_attempts",
                "last_sync_duration_ms",
                "sync_cursor",
                "provider_metadata",
                "next_sync_at",
                "updated_at",
            ]
        )
        publish_account_sync_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
            change="mark_sync_success",
            extra={"duration_ms": account.last_sync_duration_ms},
            metadata=upstream_metadata,
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_SUCCEEDED,
            payload=build_account_sync_payload(
                account=account,
                change="sync_succeeded",
                extra={"duration_ms": account.last_sync_duration_ms},
            ),
            metadata=upstream_metadata,
        )
        return account

    if mode == "stale":
        account.mark_sync_stale(commit=True)
        publish_account_sync_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
            change="mark_sync_stale",
            metadata=upstream_metadata,
        )
        return account

    account.mark_sync_error(message=message or "sync_failed", commit=False)
    if next_sync_at is not None:
        account.next_sync_at = next_sync_at
    elif retry_in_minutes:
        account.schedule_next_sync(delay_minutes=retry_in_minutes, commit=False)
    account.save(update_fields=["sync_status", "sync_error_message", "last_sync_status_at", "sync_attempts", "next_sync_at", "updated_at"])
    publish_account_sync_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
        change="mark_sync_error",
        extra={"message": account.sync_error_message, "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None},
        metadata=upstream_metadata,
    )
    publish_account_event(
        account=account,
        event_type=AccountDomainEventTypes.ACCOUNT_SYNC_FAILED,
        payload=build_account_sync_payload(
            account=account,
            change="sync_failed",
            extra={
                "message": account.sync_error_message,
                "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None,
            },
        ),
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

    result = revoke_provider_integration_access_for_user(
        user=user,
        provider=provider,
        legal_reason=consent_type or "consent_revoked",
    )
    result["trigger_event_type"] = upstream_event.get("type", "")
    result["consent_type"] = consent_type
    return result
