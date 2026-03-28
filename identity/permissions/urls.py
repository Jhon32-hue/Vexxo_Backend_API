from django.urls import include, path
from rest_framework.routers import DefaultRouter

from identity.permissions.views import UserPermissionGrantViewSet

router = DefaultRouter()
router.register(r"grants", UserPermissionGrantViewSet, basename="identity-permission-grants")

urlpatterns = [path("", include(router.urls))]
