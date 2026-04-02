from django.urls import path, include
from rest_framework.routers import DefaultRouter

from payments.payment_intents.views import (
    PaymentDomainEventOutboxViewSet,
    PaymentIntentViewSet,
    PaymentOperationalCaseViewSet,
    PaymentProviderCallbackReceiptViewSet,
    PaymentProviderCallbackView,
    PaymentProviderContractView,
    PaymentSettlementRecordViewSet,
    PaymentWorkerReportView,
    PayoutBatchViewSet,
)

router = DefaultRouter()
router.register(r"intents", PaymentIntentViewSet, basename="payment-intent")
router.register(r"payouts", PayoutBatchViewSet, basename="payment-payout-batch")
router.register(r"outbox-pagos", PaymentDomainEventOutboxViewSet, basename="payment-outbox")
router.register(r"callback-receipts", PaymentProviderCallbackReceiptViewSet, basename="payment-callback-receipt")
router.register(r"settlements", PaymentSettlementRecordViewSet, basename="payment-settlement")
router.register(r"operational-cases", PaymentOperationalCaseViewSet, basename="payment-operational-case")

urlpatterns = [
    path("", include(router.urls)),
    path("providers/contracts/", PaymentProviderContractView.as_view(), name="payment-provider-contracts"),
    path("providers/<str:provider>/contract/", PaymentProviderContractView.as_view(), name="payment-provider-contract"),
    path("provider-callback/", PaymentProviderCallbackView.as_view(), name="payment-provider-callback"),
    path("providers/<str:provider>/callback/", PaymentProviderCallbackView.as_view(), name="payment-provider-callback-provider"),
    path("worker-report/", PaymentWorkerReportView.as_view(), name="payment-worker-report"),
]
