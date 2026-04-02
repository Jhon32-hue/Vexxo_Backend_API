"""
Exports publicos de viewsets del modulo accounts.

Descripcion general:
- organiza la API REST de cuentas, membresias, snapshots y outbox

Analisis detallado:
- este paquete centraliza imports para que las urls del modulo no dependan de
  rutas internas demasiado especificas
"""

from .account_views import AccountViewSet
from .fallback_views import AccountBalanceFallbackViewSet
from .intelligence_views import (
    AccountCurrencyExposureViewSet,
    AccountOwnerMetricsViewSet,
    AccountPortfolioSnapshotViewSet,
    AccountProductSignalViewSet,
    AccountRiskSnapshotViewSet,
    AccountTypeDistributionViewSet,
)
from .membership_views import AccountMembershipViewSet
from .outbox_views import DomainEventOutboxViewSet
from .snapshot_views import BalanceSnapshotViewSet

__all__ = [
    "AccountCurrencyExposureViewSet",
    "AccountBalanceFallbackViewSet",
    "AccountMembershipViewSet",
    "AccountOwnerMetricsViewSet",
    "AccountPortfolioSnapshotViewSet",
    "AccountProductSignalViewSet",
    "AccountRiskSnapshotViewSet",
    "AccountViewSet",
    "AccountTypeDistributionViewSet",
    "BalanceSnapshotViewSet",
    "DomainEventOutboxViewSet",
]
