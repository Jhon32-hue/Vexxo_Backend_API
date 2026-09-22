"""
API administrativa del dominio de usuarios.

Descripcion general:
- permite a staff operar plan, estado y banderas de lifecycle del usuario

Analisis detallado:
- los cambios hechos aqui terminan pasando por el mismo modelo `User`, por lo
  que los signals de identidad emiten eventos de lifecycle y mantienen el resto
  del sistema en sincronizacion
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.users.models import UserStatus
from identity.users.domain.plan_matrix import resolve_plan_code
from identity.users.serializers.user_serializer import UserAdminSerializer
from identity.users.views.permissions import IsAdminUser

User = get_user_model()


class UserAdminViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("date_joined")
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ["plan", "status", "is_active", "is_verified", "onboarding_completed"]
    search_fields = ["username", "email", "first_name", "last_name"]

    @action(detail=True, methods=["post"])
    def set_plan(self, request, pk=None):
        user = self.get_object()
        new_plan = request.data.get("plan")
        if not new_plan:
            return Response(
                {"detail": "Hay que enviar 'plan' en el body."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_plan = resolve_plan_code(str(new_plan).strip().lower())
        if normalized_plan not in {"free", "pro", "enterprise"}:
            return Response(
                {"detail": "Plan invalido. Usa free, pro o enterprise."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.plan = normalized_plan
        user.save(update_fields=["plan", "updated_at"])
        return Response(
            {
                "detail": "Plan actualizado.",
                "plan": user.plan,
                "is_premium": user.is_premium,
            }
        )

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        from identity.sessions.services import revoke_all_active_sessions_for_user
        from security.audit import record_security_event
        from security.models import SecurityAuditEvent

        reason = str(request.headers.get("X-Support-Reason") or request.data.get("reason") or "").strip()
        if len(reason) < 8:
            return Response(
                {"detail": "X-Support-Reason o reason es obligatorio para suspender un usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = self.get_object()
        if user.status == UserStatus.SUSPENDED and not user.is_active:
            return Response(
                {"detail": "El usuario ya estaba suspendido."},
                status=status.HTTP_200_OK,
            )
        user.status = UserStatus.SUSPENDED
        user.is_active = False
        user.save(update_fields=["status", "is_active", "updated_at"])
        revoked = revoke_all_active_sessions_for_user(user, reason="user_suspended")
        record_security_event(
            event_type="identity.user.suspended",
            severity=SecurityAuditEvent.Severity.CRITICAL,
            actor=request.user,
            request=request,
            source="identity.users.admin",
            target_type="user",
            target_id=str(user.pk),
            metadata={"revoked_sessions": revoked, "reason": reason[:240]},
        )
        return Response({"detail": "Usuario suspendido.", "status": user.status, "revoked_sessions": revoked})

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        if user.status == UserStatus.ACTIVE and user.is_active:
            return Response(
                {"detail": "El usuario ya estaba activo."},
                status=status.HTTP_200_OK,
            )
        user.status = UserStatus.ACTIVE
        user.is_active = True
        user.save(update_fields=["status", "is_active", "updated_at"])
        return Response({"detail": "Usuario activado.", "status": user.status})

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        user = self.get_object()
        if user.is_verified:
            return Response({"detail": "El usuario ya estaba verificado."}, status=status.HTTP_200_OK)
        user.is_verified = True
        if user.status == UserStatus.PENDING:
            user.status = UserStatus.ACTIVE
        user.save(update_fields=["is_verified", "status", "updated_at"])
        return Response({"detail": "Usuario verificado.", "is_verified": True, "status": user.status})
