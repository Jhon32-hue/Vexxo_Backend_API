from rest_framework.routers import DefaultRouter

from identity.eventing.views import IdentityDomainEventOutboxViewSet

router = DefaultRouter()
router.register(r"outbox-identidad", IdentityDomainEventOutboxViewSet, basename="identity-outbox")

urlpatterns = router.urls
