"""
API de sesiones del usuario.

Descripcion general:
- expone lectura operativa de sesiones, revocacion y observabilidad
- agrega acciones para soporte y seguridad sin acoplarlas al flujo de auth

Analisis detallado:
- el login crea sesiones, pero administrarlas y auditarlas pertenece a este
  submodulo
- el resumen ayuda a detectar proliferacion de sesiones activas, proveedores
  usados o sesiones stale sin recalcular todo desde el frontend
"""

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.devices.models import UserDevice
from identity.sessions.models import UserSession
from identity.sessions.serializers import (
    UserSessionRegisterSerializer,
    UserSessionRevokeSerializer,
    UserSessionSerializer,
)
from identity.sessions.services import (
    revoke_session_family,
    register_user_session,
    revoke_all_active_sessions_for_user,
    revoke_user_session,
    session_summary_for_user,
    touch_session,
)


class UserSessionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSessionSerializer

    def get_queryset(self):
        qs = UserSession.objects.select_related("user", "device").all()
        if self.request.user.is_staff or self.request.user.is_superuser:
            return qs
        return qs.filter(user=self.request.user)

    @action(detail=False, methods=["post"])
    def register_session(self, request):
        serializer = UserSessionRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = None
        device_id = serializer.validated_data.get("device_id")
        if device_id:
            device = UserDevice.objects.filter(pk=device_id, user=request.user).first()
        session = register_user_session(
            user=request.user,
            request=request,
            session_key=serializer.validated_data.get("session_key"),
            refresh_jti=serializer.validated_data.get("refresh_jti", ""),
            access_jti=serializer.validated_data.get("access_jti", ""),
            session_type=serializer.validated_data.get("session_type", "password"),
            provider=serializer.validated_data.get("provider", ""),
            device=device,
            expires_at=serializer.validated_data.get("expires_at"),
            family_id=serializer.validated_data.get("family_id", ""),
            correlation_id=serializer.validated_data.get("correlation_id", ""),
            metadata=serializer.validated_data.get("metadata"),
        )
        return Response(UserSessionSerializer(session, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        session = self.get_object()
        serializer = UserSessionRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revoke_user_session(session, reason=serializer.validated_data.get("reason", "manual_revoke"))
        return Response(UserSessionSerializer(session, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def touch(self, request, pk=None):
        session = self.get_object()
        touch_session(session)
        return Response(UserSessionSerializer(session, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def active(self, request):
        qs = self.get_queryset().filter(status="active")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = UserSessionSerializer(page, many=True, context=self.get_serializer_context())
            return self.get_paginated_response(serializer.data)
        return Response(UserSessionSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["post"])
    def revoke_all(self, request):
        revoked = revoke_all_active_sessions_for_user(request.user, reason="self_service_revoke_all")
        return Response({"revoked_sessions": revoked})

    @action(detail=False, methods=["post"])
    def revoke_others(self, request):
        active_sessions = list(self.get_queryset().filter(status="active").order_by("-authenticated_at", "-created_at"))
        if not active_sessions:
            return Response({"revoked_sessions": 0})
        current = active_sessions[0]
        revoked = 0
        for session in active_sessions[1:]:
            revoke_user_session(session, reason="self_service_revoke_others")
            revoked += 1
        return Response({"current_session_id": current.pk, "revoked_sessions": revoked})

    @action(detail=False, methods=["post"])
    def revoke_family(self, request):
        family_id = str(request.data.get("family_id") or "").strip()
        revoked = revoke_session_family(family_id=family_id, reason="manual_family_revoke")
        return Response({"family_id": family_id, "revoked_sessions": revoked})

    @action(detail=False, methods=["get"])
    def summary(self, request):
        target_user = request.user
        if request.user.is_staff and request.query_params.get("user_id"):
            from django.contrib.auth import get_user_model

            target_user = get_user_model().objects.filter(pk=request.query_params.get("user_id")).first() or request.user
        return Response(session_summary_for_user(target_user))
