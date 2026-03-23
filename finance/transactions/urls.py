from django.urls import path, include
from rest_framework.routers import DefaultRouter

from finance.transactions.Views.transactions_views import (
    TransactionViewSet,
    TagViewSet,
    IncomeSourceViewSet,
    ScheduledPaymentViewSet,
    TransactionParticipantViewSet,
)

router = DefaultRouter()
router.register(r"transactions", TransactionViewSet, basename="transactions")
router.register(r"tags", TagViewSet, basename="tags")
router.register(r"income-sources", IncomeSourceViewSet, basename="income-sources")
router.register(r"scheduled-payments", ScheduledPaymentViewSet, basename="scheduled-payments")
router.register(r"transaction-participants", TransactionParticipantViewSet, basename="transaction-participants")

urlpatterns = [
    path("", include(router.urls)),
]
