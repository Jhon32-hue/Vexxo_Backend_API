from django.urls import include, path
from rest_framework.routers import DefaultRouter

from documents.links_to_transactions.views import DocumentTransactionLinkViewSet

router = DefaultRouter()
router.register("transaction-links", DocumentTransactionLinkViewSet, basename="document-transaction-link")
urlpatterns = [path("", include(router.urls))]
