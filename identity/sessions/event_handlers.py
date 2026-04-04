"""
Listeners de sesiones de identidad.

Descripcion general:
- reacciona a eventos de lifecycle y seguridad para mantener sesiones en
  estado coherente

Analisis detallado:
- si un usuario se suspende, sus sesiones activas deben dejar de ser validas
- si un dispositivo se revoca, las sesiones asociadas a ese dispositivo deben
  revocarse para evitar uso residual
"""

from __future__ import annotations

import logging

from common.domain_events import EventContext, EventNames, EventPriority, VexxoAppDomainEvent, subscribe
from identity.sessions.services import (
    revoke_all_active_sessions_for_user,
    revoke_device_sessions,
    revoke_provider_sessions_for_user,
)

logger = logging.getLogger(__name__)


@subscribe(
    EventNames.USER_SUSPENDED,
    name="identity.sessions.revoke_all_active_user_sessions",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
)
def handle_user_suspended(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    user_id = (event.payload or {}).get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    revoked = revoke_all_active_sessions_for_user(user, reason="user_suspended")
    logger.info(
        "[identity.sessions][corr=%s] Revocadas %s sesiones por suspension user_id=%s",
        event.correlation_id,
        revoked,
        user_id,
    )


@subscribe(
    EventNames.USER_DEVICE_REVOKED,
    name="identity.sessions.revoke_device_sessions",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
)
def handle_device_revoked(event: VexxoAppDomainEvent) -> None:
    device_id = (event.payload or {}).get("entity_id")
    if not device_id:
        return
    revoked = revoke_device_sessions(device_id=device_id, reason="device_revoked")
    logger.info(
        "[identity.sessions][corr=%s] Revocadas %s sesiones por device_id=%s",
        event.correlation_id,
        revoked,
        device_id,
    )


@subscribe(
    EventNames.USER_SOCIAL_UNLINKED,
    name="identity.sessions.revoke_unlinked_provider_sessions",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
)
def handle_social_unlinked(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    payload = event.payload or {}
    user_id = payload.get("user_id")
    provider = str(payload.get("provider") or "")
    if not user_id or not provider:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    revoked = revoke_provider_sessions_for_user(user=user, provider=provider, reason="social_provider_unlinked")
    logger.info(
        "[identity.sessions][corr=%s] Revocadas %s sesiones por unlink provider=%s user_id=%s",
        event.correlation_id,
        revoked,
        provider,
        user_id,
    )
