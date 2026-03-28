from django.urls import include, path
from rest_framework.routers import DefaultRouter

from identity.consents.views import UserConsentViewSet

router = DefaultRouter()
router.register(r"consentimientos", UserConsentViewSet, basename="identity-consents")

urlpatterns = [path("", include(router.urls))]
