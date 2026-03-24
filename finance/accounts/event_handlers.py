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

from common.domain_events import EventContext, EventNames, EventPriority, MindwalletDomainEvent, subscribe
from finance.accounts.services.realtime_services import ping_account_changed
from finance.accounts.services.sync_dispatch_service import enqueue_account_sync_task

logger = logging.getLogger(__name__)


def _publish_owner_realtime_signal(event: MindwalletDomainEvent, *, signal_event: str) -> None:
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


@subscribe(
    EventNames.ACCOUNT_SYNC_SCHEDULED,
    name="accounts.enqueue_scheduled_sync_task",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.HIGH,
)
def handle_account_sync_scheduled(event: MindwalletDomainEvent) -> None:
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
    EventNames.ACCOUNT_DRIFT_DETECTED,
    name="accounts.log_account_drift_detected",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.HIGH,
)
def handle_account_drift_detected(event: MindwalletDomainEvent) -> None:
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
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_primary_changed(event: MindwalletDomainEvent) -> None:
    _publish_owner_realtime_signal(
        event,
        signal_event="account.primary.changed",
    )


@subscribe(
    EventNames.ACCOUNT_ARCHIVED,
    name="accounts.publish_archived_realtime_signal",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_archived(event: MindwalletDomainEvent) -> None:
    _publish_owner_realtime_signal(
        event,
        signal_event="account.archived",
    )


@subscribe(
    EventNames.ACCOUNT_SYNC_SUCCEEDED,
    name="accounts.publish_sync_succeeded_realtime_signal",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_sync_succeeded(event: MindwalletDomainEvent) -> None:
    _publish_owner_realtime_signal(
        event,
        signal_event="account.sync.succeeded",
    )
