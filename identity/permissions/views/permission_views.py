"""
API de grants de permisos de producto.
"""

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.permissions.models import PermissionStatus, UserPermissionGrant
from identity.permissions.serializers import UserPermissionGrantSerializer, UserPermissionRevokeSerializer
from identity.permissions.services import (
    deny_permission,
    get_effective_permission_codes,
    get_effective_permission_resolution,
    grant_permission,
    permission_summary_for_user,
    revoke_permission,
)
from identity.users.services.product_access_service import capabilities_for_user, effective_plan_for_user, get_user_usage_snapshot
from identity.users.views.permissions import IsAdminUser


class UserPermissionGrantViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserPermissionGrantSerializer

    def get_queryset(self):
        qs = UserPermissionGrant.objects.select_related("user", "granted_by").all()
        if self.request.user.is_staff or self.request.user.is_superuser:
            return qs
        return qs.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in {"create", "revoke", "deny"}:
            return [permissions.IsAuthenticated(), IsAdminUser()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        grant = self.get_object()
        serializer = UserPermissionRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revoke_permission(grant, reason=serializer.validated_data.get("reason", ""))
        return Response(UserPermissionGrantSerializer(grant, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def deny(self, request, pk=None):
        grant = self.get_object()
        serializer = UserPermissionRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        deny_permission(grant, reason=serializer.validated_data.get("reason", ""))
        return Response(UserPermissionGrantSerializer(grant, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        qs = self.get_queryset().filter(user=request.user, status=PermissionStatus.GRANTED)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = UserPermissionGrantSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)
        return Response(UserPermissionGrantSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        target_user = request.user
        if request.user.is_staff and request.query_params.get("user_id"):
            from django.contrib.auth import get_user_model

            target_user = get_user_model().objects.filter(pk=request.query_params.get("user_id")).first() or request.user
        return Response(permission_summary_for_user(target_user))

    @action(detail=False, methods=["get"])
    def effective(self, request):
        return Response(
            {
                "user_id": str(request.user.pk),
                "plan": request.user.plan,
                "effective_plan": effective_plan_for_user(request.user),
                "capabilities": capabilities_for_user(request.user),
                "usage": get_user_usage_snapshot(request.user),
                "permission_codes": get_effective_permission_codes(request.user),
                "resolution": get_effective_permission_resolution(request.user),
            }
        )

    def perform_create(self, serializer):
        data = serializer.validated_data
        grant = grant_permission(
            user=data["user"],
            granted_by=self.request.user,
            data=data,
        )
        serializer.instance = grant
