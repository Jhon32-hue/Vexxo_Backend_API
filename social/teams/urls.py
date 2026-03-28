from django.urls import path, include
from rest_framework.routers import DefaultRouter

from social.teams.Views.team_views import TeamViewSet, MembershipViewSet

router = DefaultRouter()
router.register(r"equipos", TeamViewSet, basename="equipo")
router.register(r"miembros", MembershipViewSet, basename="miembro-equipo")

urlpatterns = [
    path("", include(router.urls)),
]
