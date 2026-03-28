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

from common.domain_events import EventContext, EventNames, EventPriority, MindwalletDomainEvent, subscribe
from identity.users.services.bootstrap_service import bootstrap_registered_user, ensure_welcome_alerts

logger = logging.getLogger(__name__)


@subscribe(
    EventNames.USER_REGISTERED,
    name="users.bootstrap_registered_user",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
)
def handle_user_registered(event: MindwalletDomainEvent) -> None:
    user_id = (event.payload or {}).get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    bootstrap_registered_user(user)


@subscribe(
    EventNames.USER_ONBOARDING_COMPLETED,
    name="users.create_onboarding_completion_alert",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
)
def handle_user_onboarding_completed(event: MindwalletDomainEvent) -> None:
    user_id = (event.payload or {}).get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    ensure_welcome_alerts(user)
    logger.info("[users.onboarding] onboarding_completed user_id=%s", user.pk)
