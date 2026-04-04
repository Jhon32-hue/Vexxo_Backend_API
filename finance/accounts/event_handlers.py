"""
Listeners locales del modulo accounts.

Descripcion general:
- reacciona a eventos de cuentas que deben transformarse en acciones internas
  o infraestructura externa
- mantiene desacopladas las vistas del detalle operativo de sincronizacion

Analisis detallado:
- el caso principal actual es `accounts.sync.scheduled.v1`: cuando se agenda un
  sync, este listener puede convertirlo en una Cloud Task hacia un worker de
  integraciones
- tambien se emiten senales realtime para cambios importantes del dominio que
  la UI puede reflejar sin depender de polling costoso del agregado completo
"""

from __future__ import annotations

import logging

from common.domain_events import EventContext, EventNames, EventPriority, VexxoAppDomainEvent, subscribe
from django.utils import timezone

from finance.accounts.services.intelligence_dispatch_service import dispatch_account_intelligence_refresh
from finance.accounts.services.realtime_services import ping_account_changed
from finance.accounts.services.sync_dispatch_service import enqueue_account_sync_task
from finance.accounts.services.user_integration_service import (
    disable_auto_sync_for_user,
    ensure_user_financial_home,
    refresh_user_accounts_projection,
    revoke_provider_integration_access_for_user,
    sync_user_currency_to_accounts,
)

logger = logging.getLogger(__name__)


def _publish_owner_realtime_signal(event: VexxoAppDomainEvent, *, signal_event: str) -> None:
    payload = event.payload or {}
    owner_id = payload.get("owner_id")
    account_id = payload.get("account_id")
    if not owner_id or not account_id:
        return

    ping_account_changed(
        owner_id=owner_id,
        account_id=account_id,
        event=signal_event,
        extra={
            "domain_event_type": event.type,
            "correlation_id": event.correlation_id,
            "payload": payload,
        },
    )


def _provider_from_permission_payload(payload: dict) -> str:
    explicit_provider = str(payload.get("provider") or "").strip()
    if explicit_provider:
        return explicit_provider

    scope_id = str(payload.get("scope_id") or "").strip()
    if not scope_id:
        return ""

    parts = scope_id.split(":")
    if len(parts) < 2:
        return ""

    provider = parts[1].strip()
    return "" if provider == "global" else provider


@subscribe(
    "accounts.*",
    name="accounts.refresh_owner_account_intelligence",
    run_async=False,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.LOW,
)
def handle_any_account_event_refresh_intelligence(event: VexxoAppDomainEvent) -> None:
    owner_id = (event.payload or {}).get("owner_id")
    if not owner_id:
        return
    try:
        minute_bucket = timezone.now().strftime("%Y%m%d%H%M")
        dispatch_account_intelligence_refresh(
            event=event,
            owner_id=owner_id,
            task_name_suffix=f"{owner_id}-{minute_bucket}",
            source="accounts.event_handlers.pattern_refresh",
        )
    except Exception:
        logger.exception(
            "[accounts.intelligence][corr=%s] Error recalculando proyecciones owner_id=%s event=%s",
            event.correlation_id,
            owner_id,
            event.type,
        )


@subscribe(
    EventNames.ACCOUNT_SYNC_SCHEDULED,
    name="accounts.enqueue_scheduled_sync_task",
    run_async=False,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.HIGH,
    required=True,
)
def handle_account_sync_scheduled(event: VexxoAppDomainEvent) -> None:
    try:
        payload = event.payload or {}
        next_sync_at = str(payload.get("next_sync_at") or "immediate")
        task_suffix = f"{payload.get('account_id', 'na')}-{next_sync_at}"
        enqueue_account_sync_task(
            event=event,
            task_name_suffix=task_suffix,
        )
    except Exception:
        logger.exception(
            "[accounts.sync][corr=%s] Error creando Cloud Task para account_id=%s",
            event.correlation_id,
            (event.payload or {}).get("account_id"),
        )


@subscribe(
    EventNames.ACCOUNT_BALANCE_UPDATED,
    name="accounts.publish_balance_updated_realtime_signal",
    run_async=False,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_balance_updated(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    owner_id = payload.get("owner_id")
    account_id = payload.get("account_id")
    if not owner_id or not account_id:
        return

    ping_account_changed(
        owner_id=owner_id,
        account_id=account_id,
        event="account.balance.changed",
        extra={
            "reason": payload.get("reason"),
            "transaction_id": payload.get("transaction_id"),
            "domain_event_type": event.type,
            "correlation_id": event.correlation_id,
        },
    )


@subscribe(
    EventNames.ACCOUNT_DRIFT_DETECTED,
    name="accounts.log_account_drift_detected",
    run_async=False,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.HIGH,
)
def handle_account_drift_detected(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    logger.warning(
        "[accounts.drift][corr=%s] account_id=%s drift_abs=%s source=%s threshold=%s",
        event.correlation_id,
        payload.get("account_id"),
        payload.get("drift_abs"),
        payload.get("source"),
        payload.get("drift_threshold"),
    )


@subscribe(
    EventNames.ACCOUNT_PRIMARY_CHANGED,
    name="accounts.publish_primary_changed_realtime_signal",
    run_async=False,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_primary_changed(event: VexxoAppDomainEvent) -> None:
    _publish_owner_realtime_signal(
        event,
        signal_event="account.primary.changed",
    )


@subscribe(
    EventNames.ACCOUNT_ARCHIVED,
    name="accounts.publish_archived_realtime_signal",
    run_async=False,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_archived(event: VexxoAppDomainEvent) -> None:
    _publish_owner_realtime_signal(
        event,
        signal_event="account.archived",
    )


@subscribe(
    EventNames.ACCOUNT_SYNC_SUCCEEDED,
    name="accounts.publish_sync_succeeded_realtime_signal",
    run_async=False,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_sync_succeeded(event: VexxoAppDomainEvent) -> None:
    _publish_owner_realtime_signal(
        event,
        signal_event="account.sync.succeeded",
    )


@subscribe(
    EventNames.USER_REGISTERED,
    name="accounts.bootstrap_user_financial_home",
    run_async=False,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
    required=True,
)
def handle_user_registered(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    owner_id = (event.payload or {}).get("user_id")
    if not owner_id:
        return
    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return
    ensure_user_financial_home(user)


@subscribe(
    EventNames.USER_PLAN_CHANGED,
    name="accounts.handle_user_plan_changed",
    run_async=False,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
    required=True,
)
def handle_user_plan_changed(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    owner_id = (event.payload or {}).get("user_id")
    if not owner_id:
        return
    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return
    refresh_user_accounts_projection(user)


@subscribe(
    EventNames.USER_CURRENCY_CHANGED,
    name="accounts.handle_user_currency_changed",
    run_async=False,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
    required=True,
)
def handle_user_currency_changed(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    payload = event.payload or {}
    owner_id = payload.get("user_id")
    if not owner_id:
        return
    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return
    before = payload.get("before") or {}
    sync_user_currency_to_accounts(
        user=user,
        previous_currency=before.get("preferred_currency"),
    )


@subscribe(
    EventNames.USER_SUSPENDED,
    name="accounts.handle_user_suspended",
    run_async=False,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
    required=True,
)
def handle_user_suspended(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    owner_id = (event.payload or {}).get("user_id")
    if not owner_id:
        return
    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return
    disable_auto_sync_for_user(user)


@subscribe(
    EventNames.USER_ACTIVATED,
    name="accounts.handle_user_activated",
    run_async=False,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
    required=True,
)
def handle_user_activated(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    owner_id = (event.payload or {}).get("user_id")
    if not owner_id:
        return
    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        return
    refresh_user_accounts_projection(user)


@subscribe(
    EventNames.USER_PERMISSION_REVOKED,
    name="accounts.handle_user_permission_revoked",
    run_async=False,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
    required=True,
)
def handle_user_permission_revoked(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    payload = event.payload or {}
    user_id = payload.get("user_id")
    if not user_id:
        return

    permission_code = str(payload.get("permission_code") or "").strip()
    if permission_code not in {
        "consents.open_banking_data.enabled",
        "consents.open_banking_payments.enabled",
    }:
        return

    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return

    revoke_provider_integration_access_for_user(
        user=user,
        provider=_provider_from_permission_payload(payload),
        legal_reason="permission_revoked",
    )
