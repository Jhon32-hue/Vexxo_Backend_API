"""
Listeners persistentes de notificaciones derivados de eventos de accounts.

Descripcion general:
- convierte eventos del dominio en items de inbox persistentes
- ya no se limita a logs; usa `notifications.deliveries` como almacenamiento

Analisis detallado:
- la idea no es reemplazar alertas; las notificaciones son una capa de
  comunicacion/inbox para el usuario
- cada listener decide a quien notificar y con que mensaje segun el tipo de
  evento
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from common.domain_events import EventContext, EventNames, EventPriority, MindwalletDomainEvent, subscribe
from notifications.deliveries.services import create_notification_delivery

logger = logging.getLogger(__name__)
User = get_user_model()


def _load_user(user_id):
    if not user_id:
        return None
    return User.objects.filter(pk=user_id).first()


def _notify_user(*, user_id, title: str, message: str, event: MindwalletDomainEvent, payload: dict):
    user = _load_user(user_id)
    if not user:
        return
    target_user_id = payload.get("user_id") or payload.get("owner_id") or user.id
    dedupe_key = f"{event.type}:{payload.get('account_id')}:{target_user_id}:{event.correlation_id or event.id}"
    create_notification_delivery(
        owner=user,
        title=title,
        message=message,
        event_type=event.type,
        source="notifications.listeners.event_handlers",
        payload=payload,
        dedupe_key=dedupe_key,
    )
    logger.info(
        "[notifications][persisted][corr=%s] event=%s owner_id=%s",
        event.correlation_id,
        event.type,
        user.id,
    )


@subscribe(
    EventNames.ACCOUNT_MEMBERSHIP_INVITED,
    name="notifications.handle_account_membership_invited",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_membership_invited(event: MindwalletDomainEvent) -> None:
    payload = event.payload or {}
    _notify_user(
        user_id=payload.get("user_id"),
        title="Te compartieron una cuenta",
        message="Tienes una nueva invitacion para colaborar en una cuenta financiera.",
        event=event,
        payload=payload,
    )


@subscribe(
    EventNames.ACCOUNT_MEMBERSHIP_ACCEPTED,
    name="notifications.handle_account_membership_accepted",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_membership_accepted(event: MindwalletDomainEvent) -> None:
    payload = event.payload or {}
    _notify_user(
        user_id=payload.get("owner_id"),
        title="Invitacion aceptada",
        message="Un colaborador acepto la invitacion a una de tus cuentas compartidas.",
        event=event,
        payload=payload,
    )


@subscribe(
    EventNames.ACCOUNT_MEMBERSHIP_REVOKED,
    name="notifications.handle_account_membership_revoked",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_membership_revoked(event: MindwalletDomainEvent) -> None:
    payload = event.payload or {}
    _notify_user(
        user_id=payload.get("user_id"),
        title="Acceso revocado",
        message="Tu acceso a una cuenta compartida fue revocado o finalizado.",
        event=event,
        payload=payload,
    )


@subscribe(
    EventNames.ACCOUNT_PRIMARY_CHANGED,
    name="notifications.handle_account_primary_changed",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_primary_changed(event: MindwalletDomainEvent) -> None:
    payload = event.payload or {}
    _notify_user(
        user_id=payload.get("owner_id"),
        title="Cuenta principal actualizada",
        message=f"La cuenta {payload.get('name') or 'financiera'} ahora es tu cuenta principal.",
        event=event,
        payload=payload,
    )


@subscribe(
    EventNames.ACCOUNT_ARCHIVED,
    name="notifications.handle_account_archived",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_archived(event: MindwalletDomainEvent) -> None:
    payload = event.payload or {}
    _notify_user(
        user_id=payload.get("owner_id"),
        title="Cuenta archivada",
        message=f"La cuenta {payload.get('name') or 'financiera'} fue archivada.",
        event=event,
        payload=payload,
    )


@subscribe(
    EventNames.ACCOUNT_SYNC_SUCCEEDED,
    name="notifications.handle_account_sync_succeeded",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.LOW,
)
def handle_account_sync_succeeded(event: MindwalletDomainEvent) -> None:
    payload = event.payload or {}
    _notify_user(
        user_id=payload.get("owner_id"),
        title="Sincronizacion completada",
        message=f"La cuenta {payload.get('name') or 'financiera'} se sincronizo correctamente.",
        event=event,
        payload=payload,
    )
