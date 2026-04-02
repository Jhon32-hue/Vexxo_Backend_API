"""
Rutas REST del modulo accounts.

Descripcion general:
- publica la API de cuentas, membresias, snapshots de balance, fallbacks y outbox

Analisis detallado:
- `cuentas` sigue siendo el entrypoint principal del modulo financiero
- `membresias-cuenta` modela colaboracion y permisos compartidos
- `snapshots-balance` expone reconciliacion operativa
- `fallbacks-balance-cuenta` expone degradaciones del flujo incremental
- `outbox-cuentas` ofrece observabilidad y soporte sobre eventos del dominio
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from finance.accounts.views import (
    AccountBalanceFallbackViewSet,
    AccountCurrencyExposureViewSet,
    AccountMembershipViewSet,
    AccountOwnerMetricsViewSet,
    AccountPortfolioSnapshotViewSet,
    AccountProductSignalViewSet,
    AccountRiskSnapshotViewSet,
    AccountTypeDistributionViewSet,
    AccountViewSet,
    BalanceSnapshotViewSet,
    DomainEventOutboxViewSet,
)

router = DefaultRouter()
router.register(r"cuentas", AccountViewSet, basename="cuentas")
router.register(r"membresias-cuenta", AccountMembershipViewSet, basename="account-memberships")
router.register(r"snapshots-balance", BalanceSnapshotViewSet, basename="account-balance-snapshots")
router.register(r"fallbacks-balance-cuenta", AccountBalanceFallbackViewSet, basename="account-balance-fallbacks")
router.register(r"outbox-cuentas", DomainEventOutboxViewSet, basename="account-outbox")
router.register(r"snapshots-portafolio-cuenta", AccountPortfolioSnapshotViewSet, basename="account-portfolio-snapshots")
router.register(r"snapshots-riesgo-cuenta", AccountRiskSnapshotViewSet, basename="account-risk-snapshots")
router.register(r"senales-producto-cuenta", AccountProductSignalViewSet, basename="account-product-signals")
router.register(r"metricas-owner-cuenta", AccountOwnerMetricsViewSet, basename="account-owner-metrics")
router.register(r"exposiciones-moneda-cuenta", AccountCurrencyExposureViewSet, basename="account-currency-exposures")
router.register(r"distribuciones-tipo-cuenta", AccountTypeDistributionViewSet, basename="account-type-distributions")

urlpatterns = [
    path("", include(router.urls)),
]
