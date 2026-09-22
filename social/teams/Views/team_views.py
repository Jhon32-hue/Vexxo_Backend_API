from django.db.models import Q
from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied

from social.teams.models import Team, Membership
from social.teams.Serializers.team_serializers import TeamSerializer, MembershipSerializer


class TeamViewSet(viewsets.ModelViewSet):
    """
    - Lista solo los equipos en los que el usuario es miembro.
    - Al crear un equipo, se asigna automáticamente como owner + membership.
    """

    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Equipos donde el usuario es miembro (activo)
        return Team.objects.filter(
            Q(owner=user) | Q(memberships__user=user, memberships__is_active=True)
        ).distinct()

    def perform_create(self, serializer):
        user = self.request.user
        team = serializer.save(owner=user)

        # Crea membership como owner si no existe
        Membership.objects.get_or_create(
            team=team,
            user=user,
            defaults={"role": "owner", "is_active": True},
        )

    def perform_destroy(self, instance):
        # Solo el owner puede borrar el equipo
        if instance.owner != self.request.user:
            raise PermissionDenied("Solo el propietario puede eliminar este equipo.")
        return super().perform_destroy(instance)

class MembershipViewSet(viewsets.ModelViewSet):
    """
    Gestiona miembros de los equipos.

    Reglas:
      - Solo puedes ver/editar miembros de equipos donde tú eres owner.
    """

    serializer_class = MembershipSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        return Membership.objects.filter(
            team__owner=user
        ).select_related("team", "user")

    def perform_update(self, serializer):
        membership = self.get_object()
        if membership.team.owner_id != self.request.user.pk:
            raise PermissionDenied("Solo el propietario puede modificar miembros.")
        if membership.role == "owner":
            raise PermissionDenied("La membresia del propietario no se modifica desde esta API.")
        serializer.save()
