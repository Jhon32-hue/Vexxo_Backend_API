"""
Exports publicos del dominio de cuentas.

Descripcion general:
- agrupa modelos, enums y objetos auxiliares del bounded context de accounts

Analisis detallado:
- funciona como facade publica del dominio de cuentas
- evita que el resto del sistema dependa de rutas internas demasiado concretas
- expone tanto la entidad principal (`Account`) como piezas auxiliares de
  consistencia y operacion (`AccountMembership`, `BalanceSnapshot`,
  `DomainEventOutbox`)
"""

from .account import (
    Account,
    AccountAccess,
    AccountAccessRole,
    AccountOwnership,
    AccountRole,
    AccountStatus,
    AccountType,
    AccountVisibility,
    GoalStrategy,
    RiskLevel,
    SharedScopeType,
    SyncStatus,
)
from .balance_snapshot import BalanceSnapshot
from .membership import AccountMembership
from .outbox import DomainEventOutbox

__all__ = [
    "Account",
    "AccountAccess",
    "AccountAccessRole",
    "AccountMembership",
    "AccountOwnership",
    "AccountRole",
    "AccountStatus",
    "AccountType",
    "AccountVisibility",
    "BalanceSnapshot",
    "DomainEventOutbox",
    "GoalStrategy",
    "RiskLevel",
    "SharedScopeType",
    "SyncStatus",
]
