"""
Listeners de grants de identidad.

Descripcion general:
- materializa grants derivados por plan y por consentimiento
- evita que la politica de producto quede duplicada entre `users`, `accounts`
  y controladores HTTP
"""

from __future__ import annotations

from common.domain_events import EventContext, EventNames, EventPriority, VexxoAppDomainEvent, subscribe
from identity.permissions.services import sync_consent_permissions_for_user, sync_plan_permissions_for_user


@subscribe(
    EventNames.USER_REGISTERED,
    name="identity.permissions.sync_plan_permissions_on_register",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
)
def handle_user_registered(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    user_id = (event.payload or {}).get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    sync_plan_permissions_for_user(user)


@subscribe(
    EventNames.USER_PLAN_CHANGED,
    name="identity.permissions.sync_plan_permissions_on_change",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
)
def handle_user_plan_changed(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    user_id = (event.payload or {}).get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    sync_plan_permissions_for_user(user)


@subscribe(
    EventNames.USER_CONSENT_GRANTED,
    name="identity.permissions.sync_consent_permissions_granted",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
)
def handle_user_consent_granted(event: VexxoAppDomainEvent) -> None:
    from django.contrib.auth import get_user_model

    payload = event.payload or {}
    user_id = payload.get("user_id")
    if not user_id:
        return
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    sync_consent_permissions_for_user(
        user=user,
        consent_type=str(payload.get("consent_type") or ""),
        granted=True,
        provider=str(payload.get("provider") or ""),
        scope_code=str(payload.get("scope_code") or ""),
    )


@subscribe(
    EventNames.USER_CONSENT_REVOKED,
    name="identity.permissions.sync_consent_permissions_revoked",
    run_async=True,
    contexts=[EventContext.IDENTITY],
    priority=EventPriority.NORMAL,
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
    sync_consent_permissions_for_user(
        user=user,
        consent_type=str(payload.get("consent_type") or ""),
        granted=False,
        provider=str(payload.get("provider") or ""),
        scope_code=str(payload.get("scope_code") or ""),
    )
