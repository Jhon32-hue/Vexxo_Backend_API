from rest_framework import serializers
from django.contrib.auth import get_user_model

from social.teams.models import Team, Membership

User = get_user_model()


class MembershipSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)

    class Meta:
        model = Membership
        fields = [
            "id",
            "team",
            "team_name",
            "user",
            "user_username",
            "role",
            "is_active",
            "joined_at",
        ]
        read_only_fields = ["team", "user", "joined_at"]

    def validate_role(self, value):
        if value == "owner":
            raise serializers.ValidationError("El rol owner no se asigna desde membresias.")
        return value

class TeamSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    members_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "description",
            "is_personal",
            "owner",
            "owner_username",
            "members_count",
            "created_at",
        ]
        read_only_fields = ["owner", "owner_username", "members_count", "created_at"]

    def create(self, validated_data):
        """
        El owner siempre será el usuario autenticado.
        """
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["owner"] = request.user
        return super().create(validated_data)
