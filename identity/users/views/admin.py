# users/views/admin.py
from django.contrib.auth import get_user_model
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.users.serializers.user_serializer import UserAdminSerializer
from identity.users.views.permissions import IsAdminUser

User = get_user_model()


class UserAdminViewSet(viewsets.ModelViewSet):
    """
    Panel de administración (API) para staffs/superusers.

    Permite:
    - listar y buscar usuarios
    - cambiar plan y overrides
    - suspender / reactivar usuario
    """

    queryset = User.objects.all().order_by("date_joined")
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ["plan", "is_active", "is_verified", "is_premium"]
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

        user.plan = new_plan
        user.is_premium = new_plan in ("plus", "pro")
        user.save(update_fields=["plan", "is_premium", "updated_at"])
        return Response(
            {
                "detail": "Plan actualizado.",
                "plan": user.plan,
                "is_premium": user.is_premium,
            }
        )

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        """
        Suspende al usuario (is_active=False).
        """
        user = self.get_object()
        if not user.is_active:
            return Response(
                {"detail": "El usuario ya estaba suspendido."},
                status=status.HTTP_200_OK,
            )
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])
        return Response({"detail": "Usuario suspendido."})

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """
        Reactiva al usuario (is_active=True).
        """
        user = self.get_object()
        if user.is_active:
            return Response(
                {"detail": "El usuario ya estaba activo."},
                status=status.HTTP_200_OK,
            )
        user.is_active = True
        user.save(update_fields=["is_active", "updated_at"])
        return Response({"detail": "Usuario activado."})
