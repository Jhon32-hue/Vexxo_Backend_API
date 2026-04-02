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
from .account_access import AccountAccess, AccountAccessRole
from .balance_snapshot import BalanceSnapshot
from .fallback import AccountBalanceFallback
from .invitation import AccountInvitation
from .intelligence import (
    AccountCurrencyExposure,
    AccountIntelligenceDispatchState,
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
    "AccountBalanceFallback",
    "AccountDataOrigin",
    "AccountInvitation",
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
    "AccountIntelligenceDispatchState",
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
