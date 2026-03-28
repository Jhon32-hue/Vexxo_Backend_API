from django.urls import include, path
from rest_framework.routers import DefaultRouter

from identity.devices.views import UserDeviceViewSet

router = DefaultRouter()
router.register(r"dispositivos", UserDeviceViewSet, basename="identity-devices")

urlpatterns = [path("", include(router.urls))]
