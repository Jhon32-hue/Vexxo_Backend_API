"""
Listeners persistentes de notificaciones derivados de eventos de dominio.

Descripcion general:
- convierte eventos del dominio en items de inbox persistentes
- ya no se limita a logs; usa `notifications.deliveries` como almacenamiento

Analisis detallado:
- la idea no es reemplazar alertas; las notificaciones son una capa de
  comunicacion/inbox para el usuario
- cada listener decide a quien notificar y con que mensaje segun el tipo de
  evento, hoy principalmente para `accounts` y `payments`
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from common.domain_events import EventContext, EventNames, EventPriority, VexxoAppDomainEvent, subscribe
from notifications.deliveries.models import NotificationCategory
from notifications.deliveries.services import create_notification_delivery
from notifications.preferences.services import get_or_create_notification_preferences
from notifications.templates.catalog import (
    minimized_notification_payload,
    resolve_notification_definition,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def _load_user(user_id):
    if not user_id:
        return None
    return User.objects.filter(pk=user_id).first()


def _notify_user(
    *,
    user_id,
    title: str,
    message: str,
    event: VexxoAppDomainEvent,
    payload: dict,
    dedupe_key: str = "",
):
    definition = resolve_notification_definition(event.type)
    if definition is not None:
        user_id = payload.get(definition.recipient_field) or user_id
    user = _load_user(user_id)
    if not user:
        return
    if definition is not None:
        preferences = get_or_create_notification_preferences(user)
        if not preferences.in_app_enabled and definition.category != NotificationCategory.SECURITY:
            return
        event_reference = str((event.metadata or {}).get("outbox_event_id") or event.id)
        normalized_dedupe = f"notification:{definition.key}:{user.pk}:{event_reference}"
        create_notification_delivery(
            owner=user,
            notification_key=definition.key,
            category=definition.category,
            priority=definition.priority,
            template_key=definition.key,
            template_version=definition.version,
            action_path=definition.action_path,
            title=definition.render_title(payload),
            message=definition.render_message(payload),
            event_type=event.type,
            source="notifications.listeners.catalog",
            payload=minimized_notification_payload(definition, event),
            dedupe_key=normalized_dedupe,
        )
        return
    target_user_id = payload.get("user_id") or payload.get("owner_id") or user.id
    normalized_dedupe = dedupe_key or (
        f"{event.type}:{payload.get('account_id')}:{target_user_id}:{event.correlation_id or event.id}"
    )
    create_notification_delivery(
        owner=user,
        title=title,
        message=message,
        event_type=event.type,
        source="notifications.listeners.event_handlers",
        payload=payload,
        dedupe_key=normalized_dedupe,
    )
    logger.info(
        "[notifications][persisted][corr=%s] event=%s owner_id=%s",
        event.correlation_id,
        event.type,
        user.id,
    )


def materialize_catalog_notification(event: VexxoAppDomainEvent) -> None:
    definition = resolve_notification_definition(event.type)
    if definition is None:
        return
    payload = event.payload or {}
    _notify_user(
        user_id=payload.get(definition.recipient_field),
        title="",
        message="",
        event=event,
        payload=payload,
    )


@subscribe("users.*", name="notifications.catalog.identity", run_async=True, contexts=[EventContext.IDENTITY])
@subscribe("accounts.*", name="notifications.catalog.accounts", run_async=True, contexts=[EventContext.ACCOUNTS])
@subscribe("transactions.*", name="notifications.catalog.transactions", run_async=True, contexts=[EventContext.TRANSACTIONS])
@subscribe("budgets.*", name="notifications.catalog.budgets", run_async=True, contexts=[EventContext.BUDGETS])
@subscribe("goals.*", name="notifications.catalog.goals", run_async=True, contexts=[EventContext.GOALS])
@subscribe("debts.*", name="notifications.catalog.debts", run_async=True, contexts=[EventContext.DEBTS])
@subscribe(
    "shared_expenses.*",
    name="notifications.catalog.shared_expenses",
    run_async=True,
    contexts=[EventContext.SHARED_EXPENSES],
)
@subscribe("payments.*", name="notifications.catalog.payments", run_async=True, contexts=[EventContext.PAYMENTS])
@subscribe("alerts.*", name="notifications.catalog.alerts", run_async=True, contexts=[EventContext.ALERTS])
@subscribe("documents.*", name="notifications.catalog.documents", run_async=True, contexts=[EventContext.DOCUMENTS])
def handle_catalog_event(event: VexxoAppDomainEvent) -> None:
    materialize_catalog_notification(event)


def _format_money(payload: dict) -> str:
    amount = str(payload.get("amount") or "").strip()
    currency = str(payload.get("currency") or "").strip().upper()
    if amount and currency:
        return f"{amount} {currency}"
    if amount:
        return amount
    return "el monto solicitado"


def _payment_provider_label(payload: dict) -> str:
    provider = str(payload.get("provider") or "").strip()
    return provider if provider else "el proveedor"


@subscribe(
    EventNames.ACCOUNT_CREATED,
    name="notifications.handle_account_created",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_created(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    account_name = payload.get("name") or "financiera"
    owner_id = payload.get("owner_id")
    account_id = payload.get("account_id")
    _notify_user(
        user_id=owner_id,
        title="Cuenta creada",
        message=f"La cuenta {account_name} ya esta disponible en tu espacio financiero.",
        event=event,
        payload=payload,
        dedupe_key=f"{event.type}:{account_id}:{owner_id}",
    )


@subscribe(
    EventNames.ACCOUNT_MEMBERSHIP_INVITED,
    name="notifications.handle_account_membership_invited",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.NORMAL,
)
def handle_account_membership_invited(event: VexxoAppDomainEvent) -> None:
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
def handle_account_membership_accepted(event: VexxoAppDomainEvent) -> None:
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
def handle_account_membership_revoked(event: VexxoAppDomainEvent) -> None:
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
def handle_account_primary_changed(event: VexxoAppDomainEvent) -> None:
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
def handle_account_archived(event: VexxoAppDomainEvent) -> None:
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
def handle_account_sync_succeeded(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    _notify_user(
        user_id=payload.get("owner_id"),
        title="Sincronizacion completada",
        message=f"La cuenta {payload.get('name') or 'financiera'} se sincronizo correctamente.",
        event=event,
        payload=payload,
    )


@subscribe(
    EventNames.PAYMENT_INTENT_REQUIRES_ACTION,
    name="notifications.handle_payment_intent_requires_action",
    run_async=True,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_intent_requires_action(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    owner_id = payload.get("owner_id")
    payment_intent_id = payload.get("payment_intent_id")
    _notify_user(
        user_id=owner_id,
        title="Tu pago requiere accion",
        message=(
            f"El pago por {_format_money(payload)} con {_payment_provider_label(payload)} "
            "requiere una accion adicional para continuar."
        ),
        event=event,
        payload=payload,
        dedupe_key=f"{event.type}:{payment_intent_id}:{owner_id}",
    )


@subscribe(
    EventNames.PAYMENT_INTENT_FAILED,
    name="notifications.handle_payment_intent_failed",
    run_async=True,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.HIGH,
)
def handle_payment_intent_failed(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    owner_id = payload.get("owner_id")
    payment_intent_id = payload.get("payment_intent_id")
    failure_message = str(payload.get("failure_message") or "").strip()
    if failure_message:
        message = (
            f"El pago por {_format_money(payload)} con {_payment_provider_label(payload)} fallo: "
            f"{failure_message}"
        )
    else:
        message = f"El pago por {_format_money(payload)} con {_payment_provider_label(payload)} no pudo completarse."
    _notify_user(
        user_id=owner_id,
        title="Pago fallido",
        message=message,
        event=event,
        payload=payload,
        dedupe_key=f"{event.type}:{payment_intent_id}:{owner_id}",
    )
