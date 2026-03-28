"""
Facade publica del dominio de accounts.

Descripcion general:
- expone enums, guardas y contratos de eventos del bounded context

Analisis detallado:
- este paquete evita imports dispersos y ayuda a que el resto del backend vea
  `accounts.domain` como una interfaz clara de reglas y eventos
"""

from .enums import AccountAccessMode, AccountMembershipRole, BalanceChangeReason
from .events import (
    AccountDomainEventTypes,
    build_account_balance_payload,
    build_account_core_payload,
    build_account_lifecycle_payload,
    build_account_membership_payload,
    build_account_snapshot_payload,
    build_account_sync_payload,
    get_account_event_catalog,
    get_account_event_governance,
    get_account_event_runtime,
)
from .guards import (
    account_creation_limit_errors,
    get_account_plan_limits,
    get_account_plan_snapshot,
    get_account_plan_usage,
    primary_account_limit_errors,
    resolve_account_plan,
)

__all__ = [
    "AccountAccessMode",
    "AccountDomainEventTypes",
    "AccountMembershipRole",
    "BalanceChangeReason",
    "account_creation_limit_errors",
    "build_account_balance_payload",
    "build_account_core_payload",
    "build_account_lifecycle_payload",
    "build_account_membership_payload",
    "build_account_snapshot_payload",
    "build_account_sync_payload",
    "get_account_event_catalog",
    "get_account_event_governance",
    "get_account_event_runtime",
    "get_account_plan_limits",
    "get_account_plan_snapshot",
    "get_account_plan_usage",
    "primary_account_limit_errors",
    "resolve_account_plan",
]
