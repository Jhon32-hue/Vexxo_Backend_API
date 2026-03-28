from django.urls import include, path
from rest_framework.routers import DefaultRouter

from identity.sessions.views import UserSessionViewSet

router = DefaultRouter()
router.register(r"sesiones", UserSessionViewSet, basename="identity-sessions")

urlpatterns = [path("", include(router.urls))]
