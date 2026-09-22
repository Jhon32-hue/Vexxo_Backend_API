from django.db.models import Q
from rest_framework import serializers

from planning.goals.models import Goal, GoalContribution, GoalMilestone
from planning.goals.services import (
    GoalLifecycleError,
    create_goal,
    create_goal_milestone,
    record_goal_contribution,
    update_goal,
)


class MetaSerializer(serializers.ModelSerializer):
    completion_percentage = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)

    class Meta:
        model = Goal
        fields = "__all__"
        read_only_fields = (
            "owner",
            "progress",
            "status",
            "active",
            "completed_at",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["account"].queryset = self.fields["account"].queryset.filter(
                owner=request.user
            )

    def validate_account(self, account):
        request = self.context.get("request")
        if account is not None and (request is None or account.owner_id != request.user.id):
            raise serializers.ValidationError("La cuenta no pertenece al usuario autenticado.")
        return account

    def create(self, validated_data):
        owner = validated_data.pop("owner", self.context["request"].user)
        try:
            return create_goal(owner=owner, **validated_data)
        except GoalLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc

    def update(self, instance, validated_data):
        try:
            return update_goal(
                goal=instance,
                owner=self.context["request"].user,
                changes=validated_data,
            )
        except GoalLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc


class GoalStatusActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class GoalContributionSerializer(serializers.ModelSerializer):
    is_reversed = serializers.BooleanField(read_only=True)

    class Meta:
        model = GoalContribution
        fields = "__all__"
        read_only_fields = (
            "owner",
            "source",
            "idempotency_key",
            "reversed_at",
            "reversal_reason",
            "created_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["goal"].queryset = Goal.objects.filter(
                Q(owner=request.user)
                | Q(shared_configuration__is_active=True, shared_configuration__team__owner=request.user)
                | Q(
                    shared_configuration__is_active=True,
                    shared_configuration__team__memberships__user=request.user,
                    shared_configuration__team__memberships__is_active=True,
                )
            ).distinct()
            self.fields["account"].queryset = self.fields["account"].queryset.filter(
                owner=request.user
            )
            self.fields["transaction"].queryset = self.fields["transaction"].queryset.filter(
                owner=request.user
            )

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        goal = attrs.get("goal")
        account = attrs.get("account")
        transaction_obj = attrs.get("transaction")
        errors = {}
        if goal is not None and (
            user is None or not self.fields["goal"].queryset.filter(pk=goal.pk).exists()
        ):
            errors["goal"] = "La meta no pertenece al usuario ni esta compartida activamente."
        if account is not None and (user is None or account.owner_id != user.id):
            errors["account"] = "La cuenta no pertenece al usuario autenticado."
        if transaction_obj is not None and (user is None or transaction_obj.owner_id != user.id):
            errors["transaction"] = "La transaccion no pertenece al usuario autenticado."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        try:
            contribution, created = record_goal_contribution(
                owner=request.user,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                transaction_obj=validated_data.pop("transaction", None),
                **validated_data,
            )
        except GoalLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        contribution._idempotent_replay = not created
        return contribution


class GoalContributionReverseSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=255)


class GoalMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoalMilestone
        fields = ("id", "goal", "name", "target_amount", "achieved_at", "created_at")
        read_only_fields = ("achieved_at", "created_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["goal"].queryset = Goal.objects.filter(owner=request.user)

    def create(self, validated_data):
        try:
            return create_goal_milestone(owner=self.context["request"].user, **validated_data)
        except GoalLifecycleError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
