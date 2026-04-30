"""
Listeners de consentimientos.

Descripcion general:
- adapta consentimientos de identidad hacia efectos operativos en otros
  bounded contexts, especialmente `finance.accounts`

Analisis detallado:
- revocar consentimiento de open banking no debe quedar solo en auditoria;
  tambien debe cortar sync automatico donde aplique
- el grant o revoke de consentimiento tambien alimenta la capa de permisos
  derivados mediante eventos separados en `identity.permissions`
"""

from __future__ import annotations

import logging

from common.domain_events import EventContext, EventNames, EventPriority, VexxoAppDomainEvent, subscribe
from finance.accounts.services.user_integration_service import (
    disable_auto_sync_for_user,
    disable_auto_sync_for_user_provider,
    refresh_user_accounts_projection,
)
from identity.consents.models import ConsentType
from identity.consents.dispatch_service import dispatch_consent_revocation_teardown

logger = logging.getLogger(__name__)


@subscribe(
    EventNames.USER_CONSENT_GRANTED,
    name="identity.consents.refresh_accounts_after_consent_granted",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
)
def handle_user_consent_granted(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    user_id = (event.payload or {}).get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    refresh_user_accounts_projection(user)


@subscribe(
    EventNames.USER_CONSENT_REVOKED,
    name="identity.consents.disable_revoked_open_banking_sync",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.HIGH,
)
def handle_user_consent_revoked(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    payload = event.payload or {}
    user_id = payload.get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return

    consent_type = str(payload.get("consent_type") or "")
    provider = str(payload.get("provider") or "").strip()
    if consent_type in {ConsentType.OPEN_BANKING_DATA, ConsentType.OPEN_BANKING_PAYMENTS}:
        try:
            teardown = dispatch_consent_revocation_teardown(
                user_id=user_id,
                provider=provider,
                consent_type=consent_type,
                event={
                    "type": event.type,
                    "correlation_id": event.correlation_id,
                    "id": event.id,
                },
            )
        except Exception:
            logger.exception(
                "[identity.consents][corr=%s] Error coordinando teardown de integracion user_id=%s provider=%s",
                event.correlation_id,
                user_id,
                provider or "*",
            )
            if provider:
                disabled = disable_auto_sync_for_user_provider(user=user, provider=provider)
            else:
                disabled = disable_auto_sync_for_user(user)
            teardown = None
        else:
            disabled = int((teardown or {}).get("disabled_accounts") or 0)
        logger.info(
            "[identity.consents][corr=%s] Auto-sync deshabilitado en %s cuentas por revoke consent user_id=%s provider=%s teardown=%s",
            event.correlation_id,
            disabled,
            user_id,
            provider or "*",
            teardown,
        )
        refresh_user_accounts_projection(user)
