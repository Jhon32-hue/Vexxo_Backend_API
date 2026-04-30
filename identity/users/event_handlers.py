"""
Listeners internos del bounded context de identidad.

Descripcion general:
- escucha eventos de lifecycle del usuario y materializa defaults que no
  pertenecen a otros bounded contexts
- desacopla registro/autenticacion del detalle de bootstrap operativo

Analisis detallado:
- `identity.users` deja de crear cuentas, categorias, equipos y alertas
  directamente desde un signal monolitico
- `accounts` reacciona por su lado para crear la cuenta base y refrescar
  proyecciones; este archivo se concentra en defaults propios del arranque de
  usuario y mensajes de onboarding
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model

from common.domain_events import EventContext, EventNames, EventPriority, VexxoAppDomainEvent, subscribe
from identity.users.services.bootstrap_service import bootstrap_registered_user, ensure_welcome_alerts
from identity.users.services.communication_service import send_welcome_email_if_needed
from identity.users.services.product_usage_projection_service import (
    apply_account_usage_event_delta,
    apply_ai_usage_event_delta,
    apply_payment_usage_event_delta,
    apply_payout_usage_event_delta,
    apply_shared_membership_event_delta,
    refresh_user_usage_projection_from_event,
)

logger = logging.getLogger(__name__)


def _refresh_usage_projection(user_id, *, event: VexxoAppDomainEvent, source: str) -> None:
    refresh_user_usage_projection_from_event(user_id, event=event, source=source)


def _refresh_usage_projection_incremental(user_id, *, event: VexxoAppDomainEvent, source: str) -> None:
    event_type = str(event.type or "")

    if event_type in {
        EventNames.ACCOUNT_CREATED,
        EventNames.ACCOUNT_UPDATED,
        EventNames.ACCOUNT_CLOSED,
        EventNames.ACCOUNT_FROZEN,
        EventNames.ACCOUNT_UNFROZEN,
        EventNames.ACCOUNT_ARCHIVED,
        EventNames.ACCOUNT_UNARCHIVED,
        EventNames.ACCOUNT_EXTERNAL_LINKED,
        EventNames.ACCOUNT_EXTERNAL_UNLINKED,
    }:
        apply_account_usage_event_delta(user_id, event=event, source=source)
        return

    if event_type in {
        EventNames.ACCOUNT_MEMBERSHIP_CREATED,
        EventNames.ACCOUNT_MEMBERSHIP_INVITED,
        EventNames.ACCOUNT_MEMBERSHIP_UPDATED,
        EventNames.ACCOUNT_MEMBERSHIP_ACCEPTED,
        EventNames.ACCOUNT_MEMBERSHIP_REVOKED,
    }:
        apply_shared_membership_event_delta(user_id, event=event, source=source)
        return

    _refresh_usage_projection(user_id, event=event, source=source)


@subscribe(
    EventNames.USER_REGISTERED,
    name="users.bootstrap_registered_user",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
)
def handle_user_registered(event: VexxoAppDomainEvent) -> None:
    user_id = (event.payload or {}).get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    bootstrap_registered_user(user)
    send_welcome_email_if_needed(user)
    _refresh_usage_projection(
        user_id,
        event=event,
        source="identity.users.event_handlers.handle_user_registered",
    )


@subscribe(
    EventNames.USER_ONBOARDING_COMPLETED,
    name="users.create_onboarding_completion_alert",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
)
def handle_user_onboarding_completed(event: VexxoAppDomainEvent) -> None:
    user_id = (event.payload or {}).get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    ensure_welcome_alerts(user)
    logger.info("[users.onboarding] onboarding_completed user_id=%s", user.pk)


@subscribe(
    "accounts.*",
    name="users.refresh_usage_projection_from_accounts",
    run_async=False,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.LOW,
)
def handle_accounts_event_refresh_usage_projection(event: VexxoAppDomainEvent) -> None:
    owner_id = (event.payload or {}).get("owner_id")
    if not owner_id:
        return
    _refresh_usage_projection_incremental(
        owner_id,
        event=event,
        source="identity.users.event_handlers.handle_accounts_event_refresh_usage_projection",
    )


@subscribe(
    EventNames.ALERT_AI_ENRICHED,
    name="users.refresh_usage_projection_from_alert_ai_enriched",
    run_async=False,
    contexts=[EventContext.ALERTS],
    priority=EventPriority.LOW,
)
def handle_alert_ai_enriched_refresh_usage_projection(event: VexxoAppDomainEvent) -> None:
    owner_id = (event.payload or {}).get("owner_id")
    if not owner_id:
        return
    apply_ai_usage_event_delta(
        owner_id,
        event=event,
        source="identity.users.event_handlers.handle_alert_ai_enriched_refresh_usage_projection",
    )


@subscribe(
    "payments.*",
    name="users.refresh_usage_projection_from_payments",
    run_async=False,
    contexts=[EventContext.PAYMENTS],
    priority=EventPriority.LOW,
)
def handle_payments_event_refresh_usage_projection(event: VexxoAppDomainEvent) -> None:
    owner_id = (event.payload or {}).get("owner_id")
    if not owner_id:
        return
    if str(event.type or "") in {
        EventNames.PAYMENT_PAYOUT_REQUESTED,
        EventNames.PAYMENT_PAYOUT_SUCCEEDED,
        EventNames.PAYMENT_PAYOUT_FAILED,
    }:
        apply_payout_usage_event_delta(
            owner_id,
            event=event,
            source="identity.users.event_handlers.handle_payments_event_refresh_usage_projection",
        )
        return
    if str(event.type or "") not in {
        EventNames.PAYMENT_INTENT_CREATED,
        EventNames.PAYMENT_INTENT_DISPATCHED,
        EventNames.PAYMENT_INTENT_REQUIRES_ACTION,
        EventNames.PAYMENT_INTENT_PROCESSING,
        EventNames.PAYMENT_INTENT_SUCCEEDED,
        EventNames.PAYMENT_INTENT_FAILED,
        EventNames.PAYMENT_INTENT_CANCELLED,
        EventNames.PAYMENT_INTENT_SETTLED,
    }:
        return
    apply_payment_usage_event_delta(
        owner_id,
        event=event,
        source="identity.users.event_handlers.handle_payments_event_refresh_usage_projection",
    )
