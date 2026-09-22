from rest_framework import serializers

from social.invitations.models import TeamInvitation
from social.invitations.services import issue_team_invitation
from social.teams.models import Team


class TeamInvitationSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    invited_by_name = serializers.CharField(source="invited_by.display_name", read_only=True)
    can_accept = serializers.SerializerMethodField()
    can_revoke = serializers.SerializerMethodField()

    class Meta:
        model = TeamInvitation
        fields = [
            "public_id", "team", "team_name", "email", "role", "status",
            "invited_by_name", "expires_at", "opened_at", "accepted_at",
            "revoked_at", "can_accept", "can_revoke", "created_at", "updated_at",
        ]
        read_only_fields = [
            "public_id", "status", "invited_by_name", "expires_at", "opened_at",
            "accepted_at", "revoked_at", "can_accept", "can_revoke", "created_at", "updated_at",
        ]

    def get_can_accept(self, obj) -> bool:
        request = self.context.get("request")
        return bool(
            request
            and request.user.is_authenticated
            and (request.user.email or "").strip().lower() == obj.email
            and obj.status in {TeamInvitation.Status.PENDING, TeamInvitation.Status.OPENED}
        )

    def get_can_revoke(self, obj) -> bool:
        request = self.context.get("request")
        return bool(
            request
            and request.user.is_authenticated
            and obj.team.owner_id == request.user.pk
            and obj.status in {TeamInvitation.Status.PENDING, TeamInvitation.Status.OPENED}
        )

    def create(self, validated_data):
        request = self.context["request"]
        return issue_team_invitation(
            team=validated_data["team"],
            invited_by=request.user,
            email=validated_data["email"],
            role=validated_data["role"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )

    def validate_team(self, team: Team):
        if team.owner_id != self.context["request"].user.pk:
            raise serializers.ValidationError("Solo el propietario puede invitar al equipo.")
        return team
