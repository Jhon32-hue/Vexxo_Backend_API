from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from social.invitations.models import TeamInvitation
from social.invitations.serializers import TeamInvitationSerializer
from social.invitations.services import accept_team_invitation, mark_team_invitation_opened, revoke_team_invitation


class TeamInvitationViewSet(viewsets.ModelViewSet):
    serializer_class = TeamInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "public_id"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        return TeamInvitation.objects.filter(
            Q(invited_user=user) | Q(email__iexact=user.email) | Q(team__owner=user) | Q(invited_by=user)
        ).select_related("team", "invited_by", "invited_user").distinct()

    @action(detail=True, methods=["post"])
    def opened(self, request, public_id=None):
        invitation = mark_team_invitation_opened(invitation=self.get_object(), actor=request.user)
        return Response(self.get_serializer(invitation).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, public_id=None):
        invitation = accept_team_invitation(invitation=self.get_object(), actor=request.user)
        return Response(self.get_serializer(invitation).data)

    @action(detail=True, methods=["post"])
    def revoke(self, request, public_id=None):
        invitation = revoke_team_invitation(invitation=self.get_object(), actor=request.user)
        return Response(self.get_serializer(invitation).data, status=status.HTTP_200_OK)
