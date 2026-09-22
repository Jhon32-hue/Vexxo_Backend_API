from django.urls import path

from api.mobile.views import MobileBootstrapView, MobileMarketsView, MobileSyncStateView


urlpatterns = [
    path("bootstrap/", MobileBootstrapView.as_view(), name="mobile-bootstrap"),
    path("sync-state/", MobileSyncStateView.as_view(), name="mobile-sync-state"),
    path("markets/", MobileMarketsView.as_view(), name="mobile-markets"),
]
