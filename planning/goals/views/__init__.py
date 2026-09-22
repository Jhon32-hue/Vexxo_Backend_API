from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from planning.goals.models import Goal, GoalContribution, GoalMilestone
from planning.goals.serializers import (
    GoalContributionReverseSerializer,
    GoalContributionSerializer,
    GoalMilestoneSerializer,
    GoalStatusActionSerializer,
    MetaSerializer,
)
from planning.goals.services import (
    GoalLifecycleError,
    build_goal_projection,
    change_goal_status,
    reverse_goal_contribution,
)


class MetaViewSet(viewsets.ModelViewSet):
    serializer_class = MetaSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        return Goal.objects.filter(owner=self.request.user).select_related("account")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def _transition(self, request, *, target_status):
        serializer = GoalStatusActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            goal = change_goal_status(
                goal=self.get_object(),
                owner=request.user,
                target_status=target_status,
                reason=serializer.validated_data.get("reason", ""),
            )
        except GoalLifecycleError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(goal).data)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return self._transition(request, target_status=Goal.Status.PAUSED)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return self._transition(request, target_status=Goal.Status.ACTIVE)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition(request, target_status=Goal.Status.CANCELED)

    @action(detail=True, methods=["get"])
    def projection(self, request, pk=None):
        try:
            return Response(build_goal_projection(goal=self.get_object(), viewer=request.user))
        except GoalLifecycleError as exc:
            raise ValidationError({"detail": str(exc)}) from exc


class GoalContributionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GoalContributionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = GoalContribution.objects.filter(owner=self.request.user).select_related(
            "goal", "account", "transaction"
        )
        goal_id = self.request.query_params.get("goal")
        return queryset.filter(goal_id=goal_id) if goal_id else queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contribution = serializer.save()
        response_status = status.HTTP_200_OK if contribution._idempotent_replay else status.HTTP_201_CREATED
        return Response(self.get_serializer(contribution).data, status=response_status)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        serializer = GoalContributionReverseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            contribution = reverse_goal_contribution(
                contribution=self.get_object(),
                owner=request.user,
                reason=serializer.validated_data["reason"],
            )
        except GoalLifecycleError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(contribution).data)


class GoalMilestoneViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GoalMilestoneSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = GoalMilestone.objects.filter(owner=self.request.user).select_related("goal")
        goal_id = self.request.query_params.get("goal")
        return queryset.filter(goal_id=goal_id) if goal_id else queryset
