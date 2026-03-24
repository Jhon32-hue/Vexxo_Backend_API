from django.urls import path

from integrations_stub.banks.views import InternalAccountSyncJobView


urlpatterns = [
    path("accounts/sync/", InternalAccountSyncJobView.as_view(), name="internal-account-sync"),
]
