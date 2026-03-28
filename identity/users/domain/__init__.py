"""
Exports publicos del dominio de usuarios.

Descripcion general:
- expone la matriz de planes y el contrato de eventos de `identity.users`

Analisis detallado:
- este facade evita imports directos a archivos internos dispersos
- sirve para que `users`, `accounts` y futuras apps usen un punto estable de
  integracion semantica
"""

from .events import (
    UserDomainEventTypes,
    build_identity_entity_payload,
    build_user_core_payload,
    build_user_lifecycle_payload,
    build_user_social_auth_payload,
    build_user_social_identity_payload,
    get_user_event_catalog,
    get_user_event_governance,
    get_user_event_runtime,
)
from .plan_matrix import PLAN_CAPABILITY_MATRIX, get_plan_capabilities, resolve_plan_code

__all__ = [
    "PLAN_CAPABILITY_MATRIX",
    "UserDomainEventTypes",
    "build_identity_entity_payload",
    "build_user_core_payload",
    "build_user_lifecycle_payload",
    "build_user_social_auth_payload",
    "build_user_social_identity_payload",
    "get_plan_capabilities",
    "get_user_event_catalog",
    "get_user_event_governance",
    "get_user_event_runtime",
    "resolve_plan_code",
]
