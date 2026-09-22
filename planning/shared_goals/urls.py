from django.urls import include, path
from rest_framework.routers import DefaultRouter

from planning.shared_goals.views import SharedGoalViewSet


router = DefaultRouter()
router.register(r"goals", SharedGoalViewSet, basename="shared-goal")

urlpatterns = [path("", include(router.urls))]
