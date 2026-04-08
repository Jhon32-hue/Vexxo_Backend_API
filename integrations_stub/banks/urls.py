from django.urls import path

from integrations_stub.banks.views import (
    InternalAccountIntelligenceRefreshView,
    InternalAccountSyncJobView,
    InternalConsentRevocationView,
    InternalTransactionsReconciliationResolutionView,
    InternalTransactionsSyncBatchView,
)


urlpatterns = [
    path("accounts/sync/", InternalAccountSyncJobView.as_view(), name="internal-account-sync"),
    path(
        "accounts/intelligence/refresh/",
        InternalAccountIntelligenceRefreshView.as_view(),
        name="internal-account-intelligence-refresh",
    ),
    path(
        "consents/revoke/",
        InternalConsentRevocationView.as_view(),
        name="internal-consent-revoke",
    ),
    path(
        "transactions/sync/",
        InternalTransactionsSyncBatchView.as_view(),
        name="internal-transactions-sync",
    ),
    path(
        "transactions/reconciliation/resolve/",
        InternalTransactionsReconciliationResolutionView.as_view(),
        name="internal-transactions-reconciliation-resolve",
    ),
]
