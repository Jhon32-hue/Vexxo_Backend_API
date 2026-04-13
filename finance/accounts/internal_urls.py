from django.urls import path

from finance.accounts.views.internal_sync_views import InternalAccountSyncStatusView


urlpatterns = [
    path("<int:account_id>/sync/<str:sync_status>/", InternalAccountSyncStatusView.as_view(), name="accounts-internal-sync-status"),
]
