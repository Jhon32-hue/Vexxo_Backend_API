from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from planning.goals.services import GoalLifecycleError, build_goal_projection
from planning.shared_goals.serializers import SharedGoalRevokeSerializer, SharedGoalSerializer
from planning.shared_goals.services import (
    revoke_shared_goal,
    share_goal,
    update_shared_goal_policy,
    visible_shared_goals,
)


class SharedGoalViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SharedGoalSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return visible_shared_goals(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shared, created = share_goal(user=request.user, **serializer.validated_data)
        return Response(
            self.get_serializer(shared).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        shared = update_shared_goal_policy(
            shared_goal=self.get_object(),
            user=request.user,
            contribution_policy=serializer.validated_data.get(
                "contribution_policy", self.get_object().contribution_policy
            ),
        )
        return Response(self.get_serializer(shared).data)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        serializer = SharedGoalRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shared = revoke_shared_goal(
            shared_goal=self.get_object(),
            user=request.user,
            reason=serializer.validated_data["reason"],
        )
        return Response(self.get_serializer(shared).data)

    @action(detail=True, methods=["get"])
    def projection(self, request, pk=None):
        shared = self.get_object()
        try:
            return Response(build_goal_projection(goal=shared.goal, viewer=request.user))
        except GoalLifecycleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
