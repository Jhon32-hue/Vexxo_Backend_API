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
    AccountDataOrigin,
    AccountOwnership,
    AccountRole,
    AccountSensitivityLevel,
    AccountSourcePriority,
    AccountStatus,
    AccountType,
    AccountVerificationLevel,
    AccountVisibility,
    GoalStrategy,
    RiskLevel,
    SharedScopeType,
    SyncStatus,
)
from .balance_snapshot import BalanceSnapshot
from .intelligence import (
    AccountCurrencyExposure,
    AccountOwnerMetrics,
    AccountPortfolioSnapshot,
    AccountProductSignal,
    AccountRiskSnapshot,
    AccountTypeDistribution,
)
from .membership import AccountMembership
from .outbox import DomainEventOutbox

__all__ = [
    "Account",
    "AccountAccess",
    "AccountAccessRole",
    "AccountDataOrigin",
    "AccountMembership",
    "AccountOwnership",
    "AccountOwnerMetrics",
    "AccountPortfolioSnapshot",
    "AccountProductSignal",
    "AccountRiskSnapshot",
    "AccountRole",
    "AccountSensitivityLevel",
    "AccountSourcePriority",
    "AccountCurrencyExposure",
    "AccountTypeDistribution",
    "AccountStatus",
    "AccountType",
    "AccountVerificationLevel",
    "AccountVisibility",
    "BalanceSnapshot",
    "DomainEventOutbox",
    "GoalStrategy",
    "RiskLevel",
    "SharedScopeType",
    "SyncStatus",
]
