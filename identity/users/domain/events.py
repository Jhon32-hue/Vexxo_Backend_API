"""
Contrato de eventos del dominio de usuarios.

Descripcion general:
- centraliza tipos de evento, builders de payload y catalogo operativo de
  `identity.users`
- permite que registro, onboarding, cambios de plan o moneda se integren con
  `accounts`, alerts, notifications y otros contextos mediante eventos formales

Analisis detallado:
- `identity.users` es el origen del lifecycle del usuario dentro de Vexxo
- este contrato evita que cada vista o signal publique payloads distintos para
  los mismos cambios semanticos
- al separar catalogo, governance y builders, se prepara el camino para Pub/Sub,
  workers cloud y documentacion automatizable

Que se puede hacer despues:
- agregar versionado v2 por evento si cambian payloads de forma incompatible
- incorporar JSON schema por evento para validacion automatica
"""

from __future__ import annotations

from typing import Any

from common.domain_events import EventNames


class UserDomainEventTypes:
    USER_REGISTERED = EventNames.USER_REGISTERED
    USER_PROFILE_UPDATED = EventNames.USER_PROFILE_UPDATED
    USER_PLAN_CHANGED = EventNames.USER_PLAN_CHANGED
    USER_CURRENCY_CHANGED = EventNames.USER_CURRENCY_CHANGED
    USER_ONBOARDING_COMPLETED = EventNames.USER_ONBOARDING_COMPLETED
    USER_VERIFIED = EventNames.USER_VERIFIED
    USER_SUSPENDED = EventNames.USER_SUSPENDED
    USER_ACTIVATED = EventNames.USER_ACTIVATED
    USER_SOCIAL_AUTH_PREPARED = EventNames.USER_SOCIAL_AUTH_PREPARED
    USER_SOCIAL_LINKED = EventNames.USER_SOCIAL_LINKED
    USER_SOCIAL_UNLINKED = EventNames.USER_SOCIAL_UNLINKED
    USER_DEVICE_REGISTERED = EventNames.USER_DEVICE_REGISTERED
    USER_DEVICE_TRUSTED = EventNames.USER_DEVICE_TRUSTED
    USER_DEVICE_REVOKED = EventNames.USER_DEVICE_REVOKED
    USER_SESSION_STARTED = EventNames.USER_SESSION_STARTED
    USER_SESSION_REVOKED = EventNames.USER_SESSION_REVOKED
    USER_CONSENT_GRANTED = EventNames.USER_CONSENT_GRANTED
    USER_CONSENT_REVOKED = EventNames.USER_CONSENT_REVOKED
    USER_PERMISSION_GRANTED = EventNames.USER_PERMISSION_GRANTED
    USER_PERMISSION_DENIED = EventNames.USER_PERMISSION_DENIED
    USER_PERMISSION_REVOKED = EventNames.USER_PERMISSION_REVOKED


USER_EVENT_CATALOG = {
    UserDomainEventTypes.USER_REGISTERED: {
        "category": "lifecycle",
        "description": "Se emite cuando se registra un usuario y nace su contexto operativo.",
        "emitted_by": ["users.signals"],
        "current_local_listeners": [
            "users.bootstrap_registered_user",
            "accounts.bootstrap_user_financial_home",
            "identity.permissions.sync_plan_permissions_on_register",
        ],
        "intended_consumers": ["accounts", "notifications", "alerts", "analytics"],
    },
    UserDomainEventTypes.USER_PROFILE_UPDATED: {
        "category": "profile",
        "description": "Se emite cuando cambian datos basicos del perfil del usuario.",
        "emitted_by": ["users.signals"],
        "current_local_listeners": [],
        "intended_consumers": ["analytics", "support"],
    },
    UserDomainEventTypes.USER_PLAN_CHANGED: {
        "category": "billing",
        "description": "Se emite cuando cambia el plan comercial del usuario.",
        "emitted_by": ["users.signals", "users.admin.set_plan"],
        "current_local_listeners": [
            "accounts.handle_user_plan_changed",
            "identity.permissions.sync_plan_permissions_on_change",
        ],
        "intended_consumers": ["accounts", "transactions", "analytics", "growth"],
    },
    UserDomainEventTypes.USER_CURRENCY_CHANGED: {
        "category": "profile",
        "description": "Se emite cuando cambia la moneda preferida/base del usuario.",
        "emitted_by": ["users.signals", "users.profile.update"],
        "current_local_listeners": ["accounts.handle_user_currency_changed"],
        "intended_consumers": ["accounts", "fx", "reports", "analytics"],
    },
    UserDomainEventTypes.USER_ONBOARDING_COMPLETED: {
        "category": "onboarding",
        "description": "Se emite cuando el usuario completa su onboarding principal.",
        "emitted_by": ["users.signals", "users.complete_onboarding"],
        "current_local_listeners": ["users.create_onboarding_completion_alert"],
        "intended_consumers": ["accounts", "notifications", "growth"],
    },
    UserDomainEventTypes.USER_VERIFIED: {
        "category": "security",
        "description": "Se emite cuando el usuario queda verificado.",
        "emitted_by": ["users.signals"],
        "current_local_listeners": [],
        "intended_consumers": ["accounts", "security", "audit"],
    },
    UserDomainEventTypes.USER_SUSPENDED: {
        "category": "security",
        "description": "Se emite cuando el usuario queda suspendido operativamente.",
        "emitted_by": ["users.signals", "users.admin.suspend"],
        "current_local_listeners": [
            "accounts.handle_user_suspended",
            "identity.sessions.revoke_all_active_user_sessions",
        ],
        "intended_consumers": ["accounts", "notifications", "audit"],
    },
    UserDomainEventTypes.USER_ACTIVATED: {
        "category": "security",
        "description": "Se emite cuando el usuario vuelve a estado activo.",
        "emitted_by": ["users.signals", "users.admin.activate"],
        "current_local_listeners": ["accounts.handle_user_activated"],
        "intended_consumers": ["accounts", "notifications", "audit"],
    },
    UserDomainEventTypes.USER_SOCIAL_AUTH_PREPARED: {
        "category": "auth",
        "description": "Se emite cuando se consulta o prepara un proveedor social para login/registro.",
        "emitted_by": ["users.auth.social_start"],
        "current_local_listeners": [],
        "intended_consumers": ["analytics", "audit"],
    },
    UserDomainEventTypes.USER_SOCIAL_LINKED: {
        "category": "auth",
        "description": "Se emite cuando una identidad social queda vinculada al usuario.",
        "emitted_by": ["users.auth.social_callback", "users.auth.social_link"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "analytics", "security"],
    },
    UserDomainEventTypes.USER_SOCIAL_UNLINKED: {
        "category": "auth",
        "description": "Se emite cuando una identidad social se desvincula del usuario.",
        "emitted_by": ["users.auth.social_unlink"],
        "current_local_listeners": ["identity.sessions.revoke_unlinked_provider_sessions"],
        "intended_consumers": ["audit", "analytics", "security"],
    },
    UserDomainEventTypes.USER_DEVICE_REGISTERED: {
        "category": "security",
        "description": "Se emite cuando se registra o reconoce un dispositivo del usuario.",
        "emitted_by": ["identity.devices"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "security", "notifications"],
    },
    UserDomainEventTypes.USER_DEVICE_TRUSTED: {
        "category": "security",
        "description": "Se emite cuando un dispositivo se marca como confiable.",
        "emitted_by": ["identity.devices"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "security"],
    },
    UserDomainEventTypes.USER_DEVICE_REVOKED: {
        "category": "security",
        "description": "Se emite cuando un dispositivo se revoca.",
        "emitted_by": ["identity.devices"],
        "current_local_listeners": ["identity.sessions.revoke_device_sessions"],
        "intended_consumers": ["audit", "security"],
    },
    UserDomainEventTypes.USER_SESSION_STARTED: {
        "category": "security",
        "description": "Se emite cuando se registra una sesion autentica del usuario.",
        "emitted_by": ["identity.sessions", "users.auth.login"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "security", "analytics"],
    },
    UserDomainEventTypes.USER_SESSION_REVOKED: {
        "category": "security",
        "description": "Se emite cuando se revoca una sesion del usuario.",
        "emitted_by": ["identity.sessions", "users.auth.logout"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "security"],
    },
    UserDomainEventTypes.USER_CONSENT_GRANTED: {
        "category": "consent",
        "description": "Se emite cuando el usuario otorga un consentimiento.",
        "emitted_by": ["identity.consents"],
        "current_local_listeners": [
            "identity.consents.refresh_accounts_after_consent_granted",
            "identity.permissions.sync_consent_permissions_granted",
        ],
        "intended_consumers": ["audit", "integrations", "analytics"],
    },
    UserDomainEventTypes.USER_CONSENT_REVOKED: {
        "category": "consent",
        "description": "Se emite cuando el usuario revoca un consentimiento.",
        "emitted_by": ["identity.consents"],
        "current_local_listeners": [
            "identity.consents.disable_revoked_open_banking_sync",
            "identity.permissions.sync_consent_permissions_revoked",
        ],
        "intended_consumers": ["audit", "integrations", "analytics"],
    },
    UserDomainEventTypes.USER_PERMISSION_GRANTED: {
        "category": "authorization",
        "description": "Se emite cuando se otorga un grant de permiso de producto al usuario.",
        "emitted_by": ["identity.permissions"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "analytics"],
    },
    UserDomainEventTypes.USER_PERMISSION_DENIED: {
        "category": "authorization",
        "description": "Se emite cuando un permiso queda denegado de forma explicita, normalmente por override administrativo.",
        "emitted_by": ["identity.permissions"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "analytics", "security"],
    },
    UserDomainEventTypes.USER_PERMISSION_REVOKED: {
        "category": "authorization",
        "description": "Se emite cuando se revoca un grant de permiso de producto al usuario.",
        "emitted_by": ["identity.permissions"],
        "current_local_listeners": [],
        "intended_consumers": ["audit", "analytics"],
    },
}


USER_EVENT_GOVERNANCE = {
    event_type: {
        "contract_status": "active",
        "schema_version": "v1",
        "deprecated": False,
        "deprecated_by": None,
        "visibility": "internal",
        "required_fields": ["user_id", "email", "plan", "status", "preferred_currency"],
    }
    for event_type in USER_EVENT_CATALOG
}

USER_EVENT_GOVERNANCE[UserDomainEventTypes.USER_SOCIAL_AUTH_PREPARED]["required_fields"] = [
    "provider",
    "configured",
    "authorization_url",
    "callback_url",
]
USER_EVENT_GOVERNANCE[UserDomainEventTypes.USER_SOCIAL_LINKED]["required_fields"] = [
    "user_id",
    "provider",
    "provider_user_id",
    "email",
]
USER_EVENT_GOVERNANCE[UserDomainEventTypes.USER_SOCIAL_UNLINKED]["required_fields"] = [
    "user_id",
    "provider",
    "provider_user_id",
]


def build_user_core_payload(user) -> dict[str, Any]:
    return {
        "user_id": str(user.pk),
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "full_name": user.display_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "plan": user.plan,
        "effective_plan": getattr(user, "effective_plan", user.plan),
        "status": user.status,
        "is_active": bool(user.is_active),
        "is_verified": bool(user.is_verified),
        "onboarding_completed": bool(user.onboarding_completed),
        "preferred_currency": user.preferred_currency,
        "timezone_name": user.timezone_name,
        "locale": user.locale,
        "has_paid_plan": bool(user.has_paid_plan),
    }


def build_user_lifecycle_payload(*, user, change: str, before: dict | None = None, after: dict | None = None, extra: dict | None = None) -> dict[str, Any]:
    payload = build_user_core_payload(user)
    payload["change"] = change
    if before is not None:
        payload["before"] = before
    if after is not None:
        payload["after"] = after
    if extra:
        payload.update(extra)
    return payload


def build_user_social_auth_payload(*, provider: str, configured: bool, authorization_url: str, callback_url: str, user=None) -> dict[str, Any]:
    payload = {
        "provider": provider,
        "configured": configured,
        "authorization_url": authorization_url,
        "callback_url": callback_url,
    }
    if user is not None:
        payload.update(build_user_core_payload(user))
    return payload


def build_user_social_identity_payload(*, user, provider: str, provider_user_id: str, identity_id, email: str = "", linked: bool = True, extra: dict | None = None) -> dict[str, Any]:
    payload = build_user_core_payload(user)
    payload.update(
        {
            "provider": provider,
            "provider_user_id": str(provider_user_id),
            "identity_id": str(identity_id),
            "email": email or user.email,
            "linked": bool(linked),
        }
    )
    if extra:
        payload.update(extra)
    return payload


def build_identity_entity_payload(*, user, entity_type: str, entity_id, extra: dict | None = None) -> dict[str, Any]:
    payload = build_user_core_payload(user)
    payload["entity_type"] = entity_type
    payload["entity_id"] = str(entity_id)
    if extra:
        payload.update(extra)
    return payload


def get_user_event_catalog() -> dict[str, dict[str, Any]]:
    response: dict[str, dict[str, Any]] = {}
    for event_type, entry in USER_EVENT_CATALOG.items():
        governance = USER_EVENT_GOVERNANCE.get(event_type, {})
        response[event_type] = {
            "event_type": event_type,
            **entry,
            **governance,
            "pattern_local_listeners": [],
            "effective_local_listeners": list(entry.get("current_local_listeners", [])),
        }
    return response


def get_user_event_governance() -> dict[str, dict[str, Any]]:
    return dict(USER_EVENT_GOVERNANCE)


def get_user_event_runtime() -> dict[str, Any]:
    return {
        "context": "identity",
        "pattern_listeners": [],
        "transport": {
            "persistent_outbox": True,
            "local_bus": True,
            "pubsub_if_enabled": True,
        },
    }
