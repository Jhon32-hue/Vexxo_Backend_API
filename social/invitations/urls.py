from django.urls import include, path
from rest_framework.routers import DefaultRouter

from social.invitations.views import TeamInvitationViewSet


router = DefaultRouter()
router.register("team-invitations", TeamInvitationViewSet, basename="team-invitation")

urlpatterns = [path("", include(router.urls))]
