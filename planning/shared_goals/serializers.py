from rest_framework import serializers
from django.db.models import Q

from planning.goals.models import Goal
from planning.shared_goals.models import SharedGoal
from social.teams.models import Team


class SharedGoalSerializer(serializers.ModelSerializer):
    goal_name = serializers.CharField(source="goal.name", read_only=True)
    progress = serializers.DecimalField(source="goal.progress", max_digits=14, decimal_places=2, read_only=True)
    target_amount = serializers.DecimalField(source="goal.target_amount", max_digits=14, decimal_places=2, read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)

    class Meta:
        model = SharedGoal
        fields = (
            "id",
            "goal",
            "goal_name",
            "progress",
            "target_amount",
            "team",
            "team_name",
            "contribution_policy",
            "is_active",
            "revoked_at",
            "revocation_reason",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "is_active",
            "revoked_at",
            "revocation_reason",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["goal"].queryset = Goal.objects.filter(owner=request.user)
            self.fields["team"].queryset = Team.objects.filter(
                Q(owner=request.user)
                | Q(memberships__user=request.user, memberships__is_active=True)
            ).distinct()


class SharedGoalRevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=255)
