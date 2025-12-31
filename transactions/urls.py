# transactions/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from transactions.Views.transactions_views import (
    TransactionViewSet,
    TagViewSet,
    IncomeSourceViewSet,
    ScheduledPaymentViewSet,
)

router = DefaultRouter()
router.register(r"transactions", TransactionViewSet, basename="transactions")
router.register(r"tags", TagViewSet, basename="transaction-tags")
router.register(r"income-sources", IncomeSourceViewSet, basename="income-sources")
router.register(
    r"scheduled-payments",
    ScheduledPaymentViewSet,
    basename="scheduled-payments",
)

urlpatterns = [
    path("", include(router.urls)),
]
# transactions/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from transactions.Views.transactions_views import (
    TransactionViewSet,
    TagViewSet,
    IncomeSourceViewSet,
    ScheduledPaymentViewSet,
)

router = DefaultRouter()
router.register(r"transacciones", TransactionViewSet, basename="transactions")
router.register(r"etiquetas", TagViewSet, basename="transaction-tags")
router.register(r"ingreso", IncomeSourceViewSet, basename="income-sources")
router.register(
    r"pagos-programados",
    ScheduledPaymentViewSet,
    basename="scheduled-payments",
)

urlpatterns = [
    path("", include(router.urls)),
]
