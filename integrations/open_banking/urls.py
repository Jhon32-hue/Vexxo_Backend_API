from django.urls import include, path
from rest_framework.routers import DefaultRouter

from integrations.open_banking.views import (
    OpenBankingConnectionViewSet,
    OpenBankingInstitutionListView,
    OpenBankingProviderListView,
    OpenBankingWebhookView,
)


router = DefaultRouter()
router.register("connections", OpenBankingConnectionViewSet, basename="open-banking-connection")

urlpatterns = [
    path("providers/", OpenBankingProviderListView.as_view(), name="open-banking-providers"),
    path("institutions/", OpenBankingInstitutionListView.as_view(), name="open-banking-institutions"),
    path("webhooks/<str:provider>/", OpenBankingWebhookView.as_view(), name="open-banking-webhook"),
    path("", include(router.urls)),
]
