"""
Contratos de eventos del bounded context de accounts.

Descripcion general:
- centraliza nombres, payloads base y builders de eventos del modulo
- evita que views, signals y servicios inventen estructuras distintas

Analisis detallado:
- la arquitectura de Vexxo para accounts es event-driven: el modulo publica
  cambios y otros servicios reaccionan despues via bus local, outbox y futuros
  consumidores externos
- este archivo define el contrato del dominio, no el transporte
- con estos builders, los eventos siguen siendo consistentes aunque cambie la
  infraestructura de entrega (bus local hoy, Pub/Sub/Cloud Tasks manana)

Que se puede hacer despues:
- versionar payloads mas complejos por feature
- generar esquemas JSON para consumidores externos
"""

from __future__ import annotations

from decimal import Decimal

from common.domain_events import EventNames


class AccountDomainEventTypes:
    ACCOUNT_CREATED = EventNames.ACCOUNT_CREATED
    ACCOUNT_UPDATED = EventNames.ACCOUNT_UPDATED
    ACCOUNT_CLOSED = EventNames.ACCOUNT_CLOSED
    ACCOUNT_PRIMARY_CHANGED = EventNames.ACCOUNT_PRIMARY_CHANGED
    ACCOUNT_FROZEN = EventNames.ACCOUNT_FROZEN
    ACCOUNT_UNFROZEN = EventNames.ACCOUNT_UNFROZEN
    ACCOUNT_ARCHIVED = EventNames.ACCOUNT_ARCHIVED
    ACCOUNT_UNARCHIVED = EventNames.ACCOUNT_UNARCHIVED
    ACCOUNT_RECALCULATED = EventNames.ACCOUNT_RECALCULATED
    ACCOUNT_SNAPSHOT_CREATED = EventNames.ACCOUNT_SNAPSHOT_CREATED
    ACCOUNT_DRIFT_DETECTED = EventNames.ACCOUNT_DRIFT_DETECTED
    ACCOUNT_BALANCE_UPDATED = EventNames.ACCOUNT_BALANCE_UPDATED
    ACCOUNT_EXTERNAL_LINKED = EventNames.ACCOUNT_EXTERNAL_LINKED
    ACCOUNT_EXTERNAL_UNLINKED = EventNames.ACCOUNT_EXTERNAL_UNLINKED
    ACCOUNT_SYNC_SCHEDULED = EventNames.ACCOUNT_SYNC_SCHEDULED
    ACCOUNT_SYNC_STATUS_CHANGED = EventNames.ACCOUNT_SYNC_STATUS_CHANGED
    ACCOUNT_SYNC_STARTED = EventNames.ACCOUNT_SYNC_STARTED
    ACCOUNT_SYNC_SUCCEEDED = EventNames.ACCOUNT_SYNC_SUCCEEDED
    ACCOUNT_SYNC_FAILED = EventNames.ACCOUNT_SYNC_FAILED
    ACCOUNT_MEMBERSHIP_CREATED = EventNames.ACCOUNT_MEMBERSHIP_CREATED
    ACCOUNT_MEMBERSHIP_INVITED = EventNames.ACCOUNT_MEMBERSHIP_INVITED
    ACCOUNT_MEMBERSHIP_UPDATED = EventNames.ACCOUNT_MEMBERSHIP_UPDATED
    ACCOUNT_MEMBERSHIP_ACCEPTED = EventNames.ACCOUNT_MEMBERSHIP_ACCEPTED
    ACCOUNT_MEMBERSHIP_REVOKED = EventNames.ACCOUNT_MEMBERSHIP_REVOKED


ACCOUNT_EVENT_CATALOG = [
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_CREATED,
        "category": "lifecycle",
        "description": "Se emite cuando nace una cuenta financiera en Vexxo.",
        "emitted_by": ["accounts.views.perform_create"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "analytics", "notifications", "integrations"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_UPDATED,
        "category": "lifecycle",
        "description": "Se emite cuando cambia configuracion o estado operativo de una cuenta.",
        "emitted_by": [
            "accounts.views.perform_update",
            "accounts.views.set_primary",
            "accounts.views.freeze",
            "accounts.views.unfreeze",
            "accounts.views.archive",
            "accounts.views.unarchive",
        ],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "analytics", "notifications"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_CLOSED,
        "category": "lifecycle",
        "description": "Se emite cuando una cuenta se cierra o se hace soft-delete.",
        "emitted_by": ["accounts.views.close_account", "accounts.views.perform_destroy"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "reports", "notifications"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_PRIMARY_CHANGED,
        "category": "lifecycle",
        "description": "Se emite cuando una cuenta activa pasa a ser principal.",
        "emitted_by": ["accounts.views.set_primary"],
        "current_local_listeners": [
            "notifications.handle_account_primary_changed",
            "accounts.publish_primary_changed_realtime_signal",
        ],
        "intended_consumers": ["dashboards", "notifications", "analytics"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_FROZEN,
        "category": "lifecycle",
        "description": "Se emite cuando una cuenta se congela operativamente.",
        "emitted_by": ["accounts.views.freeze"],
        "current_local_listeners": [],
        "intended_consumers": ["notifications", "risk", "analytics"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_UNFROZEN,
        "category": "lifecycle",
        "description": "Se emite cuando una cuenta vuelve a estado activo desde frozen.",
        "emitted_by": ["accounts.views.unfreeze"],
        "current_local_listeners": [],
        "intended_consumers": ["notifications", "risk", "analytics"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_ARCHIVED,
        "category": "lifecycle",
        "description": "Se emite cuando una cuenta pasa a estado archived.",
        "emitted_by": ["accounts.views.archive"],
        "current_local_listeners": [
            "notifications.handle_account_archived",
            "accounts.publish_archived_realtime_signal",
        ],
        "intended_consumers": ["reports", "notifications", "analytics"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_UNARCHIVED,
        "category": "lifecycle",
        "description": "Se emite cuando una cuenta archivada vuelve a estado activo.",
        "emitted_by": ["accounts.views.unarchive"],
        "current_local_listeners": [],
        "intended_consumers": ["reports", "notifications", "analytics"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_RECALCULATED,
        "category": "balance",
        "description": "Se emite cuando se fuerza un recalculo manual del balance.",
        "emitted_by": ["accounts.views.recalc_balance"],
        "current_local_listeners": [],
        "intended_consumers": ["support", "analytics", "audit"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_SNAPSHOT_CREATED,
        "category": "balance",
        "description": "Se emite al crear un snapshot de reconciliacion de balance.",
        "emitted_by": ["accounts.views.snapshot_create", "accounts.services.reconcile_service"],
        "current_local_listeners": [],
        "intended_consumers": ["observability", "support", "analytics"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_DRIFT_DETECTED,
        "category": "balance",
        "description": "Se emite cuando un snapshot detecta drift material entre cache y ledger.",
        "emitted_by": ["accounts.views.snapshot_create", "accounts.services.reconcile_service"],
        "current_local_listeners": ["alerts.handle_account_drift_detected"],
        "intended_consumers": ["alerts", "support", "analytics"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_BALANCE_UPDATED,
        "category": "balance",
        "description": "Se emite cuando cambia el balance cacheado o se recalcula desde ledger.",
        "emitted_by": [
            "accounts.signals",
            "accounts.use_cases",
            "accounts.views.recalc_balance",
        ],
        "current_local_listeners": ["alerts.handle_account_balance_updated"],
        "intended_consumers": ["alerts", "reports", "notifications", "wealth"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_EXTERNAL_LINKED,
        "category": "sync",
        "description": "Se emite cuando una cuenta local queda vinculada a un proveedor externo.",
        "emitted_by": ["accounts.views.link_external_source"],
        "current_local_listeners": [],
        "intended_consumers": ["integrations", "workers", "audit"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_EXTERNAL_UNLINKED,
        "category": "sync",
        "description": "Se emite cuando se remueve la vinculacion con un proveedor externo.",
        "emitted_by": ["accounts.views.unlink_external_source"],
        "current_local_listeners": [],
        "intended_consumers": ["integrations", "workers", "audit"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_SYNC_SCHEDULED,
        "category": "sync",
        "description": "Se emite cuando se agenda una corrida de sincronizacion externa.",
        "emitted_by": ["accounts.views.schedule_sync"],
        "current_local_listeners": ["accounts.enqueue_scheduled_sync_task"],
        "intended_consumers": ["sync-workers", "scheduler", "audit"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
        "category": "sync",
        "description": "Se emite cuando cambia el estado operativo del sync de una cuenta.",
        "emitted_by": [
            "accounts.views.mark_sync_running",
            "accounts.views.mark_sync_success",
            "accounts.views.mark_sync_error",
            "accounts.views.mark_sync_stale",
        ],
        "current_local_listeners": [],
        "intended_consumers": ["integrations", "observability", "notifications"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_SYNC_STARTED,
        "category": "sync",
        "description": "Se emite cuando un worker inicia la sincronizacion de una cuenta.",
        "emitted_by": ["accounts.views.mark_sync_running"],
        "current_local_listeners": [],
        "intended_consumers": ["observability", "integrations"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_SYNC_SUCCEEDED,
        "category": "sync",
        "description": "Se emite cuando una sincronizacion externa finaliza correctamente.",
        "emitted_by": ["accounts.views.mark_sync_success"],
        "current_local_listeners": [
            "notifications.handle_account_sync_succeeded",
            "accounts.publish_sync_succeeded_realtime_signal",
        ],
        "intended_consumers": ["observability", "analytics", "integrations"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_SYNC_FAILED,
        "category": "sync",
        "description": "Se emite cuando una sincronizacion externa falla.",
        "emitted_by": ["accounts.views.mark_sync_error"],
        "current_local_listeners": ["alerts.handle_account_sync_failed"],
        "intended_consumers": ["alerts", "observability", "integrations"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_CREATED,
        "category": "membership",
        "description": "Se emite cuando se agrega un colaborador a una cuenta.",
        "emitted_by": ["accounts.views.membership_create"],
        "current_local_listeners": [],
        "intended_consumers": ["notifications", "audit", "social"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_INVITED,
        "category": "membership",
        "description": "Se emite cuando la membresia se crea como invitacion pendiente.",
        "emitted_by": ["accounts.views.membership_create", "accounts.views.membership_rotate_invitation"],
        "current_local_listeners": ["notifications.handle_account_membership_invited"],
        "intended_consumers": ["notifications", "audit", "social"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_UPDATED,
        "category": "membership",
        "description": "Se emite cuando cambia el rol, permisos o invitacion de una membresia.",
        "emitted_by": [
            "accounts.views.membership_update",
            "accounts.views.membership_rotate_invitation",
        ],
        "current_local_listeners": [],
        "intended_consumers": ["notifications", "audit", "social"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_ACCEPTED,
        "category": "membership",
        "description": "Se emite cuando una invitacion a cuenta compartida es aceptada.",
        "emitted_by": ["accounts.views.membership_accept"],
        "current_local_listeners": ["notifications.handle_account_membership_accepted"],
        "intended_consumers": ["notifications", "audit", "social"],
    },
    {
        "event_type": AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_REVOKED,
        "category": "membership",
        "description": "Se emite cuando una membresia se revoca o desactiva.",
        "emitted_by": [
            "accounts.views.membership_destroy",
            "accounts.views.membership_revoke",
        ],
        "current_local_listeners": ["notifications.handle_account_membership_revoked"],
        "intended_consumers": ["notifications", "audit", "social"],
    },
]


def get_account_event_catalog() -> list[dict]:
    """
    Catalogo documentado de eventos emitidos por `finance.accounts`.
    """
    return [dict(item) for item in ACCOUNT_EVENT_CATALOG]


def get_account_event_runtime() -> dict:
    """
    Describe el camino actual de entrega de eventos del modulo.
    """
    return {
        "aggregate_type": "account",
        "transport_today": [
            "domain action / signal / viewset",
            "finance.accounts.services.outbox_service",
            "finance.accounts.services.event_service.enqueue_domain_event",
            "finance.accounts.models.outbox.DomainEventOutbox",
            "transaction.on_commit -> publish_outbox_event",
            "common.domain_events.publish_domain_event",
            "local listeners registrados con @subscribe",
            "dispatcher opcional common.gcp.pubsub_dispatcher",
            "listener opcional finance.accounts.event_handlers -> Cloud Tasks",
        ],
        "current_dispatch_mode": "local_event_bus_with_outbox_plus_optional_pubsub_and_cloud_tasks",
        "prepared_for": [
            "Pub/Sub dispatchers",
            "Cloud Run workers",
            "Cloud Tasks consumers",
        ],
    }


def build_account_core_payload(account) -> dict:
    return {
        "account_id": account.pk,
        "owner_id": account.owner_id,
        "name": account.name,
        "type": account.type,
        "role": account.role,
        "ownership": account.ownership,
        "status": account.status,
        "currency": account.currency,
        "provider": account.provider,
        "external_id": account.external_id,
        "sync_status": account.sync_status,
    }


def build_account_balance_payload(
    *,
    account,
    old_balance,
    new_balance,
    reason: str,
    transaction_id: int | None = None,
) -> dict:
    old_value = Decimal(str(old_balance))
    new_value = Decimal(str(new_balance))
    return {
        "account_id": account.pk,
        "owner_id": account.owner_id,
        "currency": account.currency,
        "old_balance": str(old_value),
        "new_balance": str(new_value),
        "delta": str(new_value - old_value),
        "reason": reason,
        "transaction_id": transaction_id,
    }


def build_account_lifecycle_payload(
    *,
    account,
    change: str,
    before: dict | None = None,
    after: dict | None = None,
    extra: dict | None = None,
) -> dict:
    payload = {
        **build_account_core_payload(account),
        "change": change,
    }
    if before is not None:
        payload["before"] = before
    if after is not None:
        payload["after"] = after
    if extra:
        payload.update(extra)
    return payload


def build_account_sync_payload(
    *,
    account,
    change: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        **build_account_core_payload(account),
        "change": change,
        "has_external_link": account.has_external_link,
        "sync_health": account.sync_health,
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
        "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None,
    }
    if extra:
        payload.update(extra)
    return payload


def build_account_membership_payload(*, membership, change: str, extra: dict | None = None) -> dict:
    payload = {
        "membership_id": membership.pk,
        "account_id": membership.account_id,
        "owner_id": membership.account.owner_id,
        "user_id": membership.user_id,
        "role": membership.role,
        "access_mode": membership.access_mode,
        "is_active": membership.is_active,
        "change": change,
        "accepted_at": membership.accepted_at.isoformat() if membership.accepted_at else None,
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
        "revoked_at": membership.revoked_at.isoformat() if membership.revoked_at else None,
    }
    if extra:
        payload.update(extra)
    return payload


def build_account_snapshot_payload(*, snapshot, change: str, drift_threshold=None, extra: dict | None = None) -> dict:
    payload = {
        **build_account_core_payload(snapshot.account),
        "snapshot_id": snapshot.pk,
        "change": change,
        "as_of": snapshot.as_of.isoformat() if snapshot.as_of else None,
        "balance_cached": str(snapshot.balance_cached),
        "balance_recomputed": str(snapshot.balance_recomputed),
        "drift": str(snapshot.drift),
        "drift_abs": str(snapshot.drift_abs),
        "is_consistent": snapshot.is_consistent,
        "tx_count": snapshot.tx_count,
        "source": snapshot.source,
        "note": snapshot.note,
        "drift_threshold": str(drift_threshold) if drift_threshold is not None else None,
    }
    if extra:
        payload.update(extra)
    return payload
