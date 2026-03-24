"""
Rutas REST del modulo accounts.

Descripcion general:
- publica la API de cuentas, membresias, snapshots de balance y outbox

Analisis detallado:
- `cuentas` sigue siendo el entrypoint principal del modulo financiero
- `membresias-cuenta` modela colaboracion y permisos compartidos
- `snapshots-balance` expone reconciliacion operativa
- `outbox-cuentas` ofrece observabilidad y soporte sobre eventos del dominio
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from finance.accounts.views import (
    AccountMembershipViewSet,
    AccountViewSet,
    BalanceSnapshotViewSet,
    DomainEventOutboxViewSet,
)

router = DefaultRouter()
router.register(r"cuentas", AccountViewSet, basename="cuentas")
router.register(r"membresias-cuenta", AccountMembershipViewSet, basename="account-memberships")
router.register(r"snapshots-balance", BalanceSnapshotViewSet, basename="account-balance-snapshots")
router.register(r"outbox-cuentas", DomainEventOutboxViewSet, basename="account-outbox")

urlpatterns = [
    path("", include(router.urls)),
]
