# alerts/views/alert_views.py
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from alerts.alerts.models.alerts import Alert, AlertStatus
from alerts.alerts.serializers.alert_serializers import AlertaSerializer


class AlertaViewSet(viewsets.ModelViewSet):
    """
    API de alertas de Mindwallet.

    - Listado y detalle de alertas del usuario autenticado.
    - Acciones para marcar como leída, resuelta o posponer (snooze).
    """

    serializer_class = AlertaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Alert.objects.filter(owner=user)

        status_param = self.request.query_params.get("status")
        severity = self.request.query_params.get("severity")
        category = self.request.query_params.get("category")
        is_active = self.request.query_params.get("is_active")

        if status_param:
            qs = qs.filter(status=status_param)

        if severity:
            qs = qs.filter(severity=severity)

        if category:
            qs = qs.filter(category=category)

        if is_active is not None:
            if is_active.lower() == "true":
                qs = qs.filter(is_active=True)
            elif is_active.lower() == "false":
                qs = qs.filter(is_active=False)

        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        """
        En principio las alertas no se crean desde el cliente,
        sino desde servicios internos. Pero si algún día lo necesitas
        (p. ej. admins), aquí se asegura el owner.
        """
        serializer.save(owner=self.request.user)

    # ===== Extra actions =====

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        alert = self.get_object()
        alert.mark_read(commit=True)
        return Response({"detail": "Alerta marcada como leída."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def mark_resolved(self, request, pk=None):
        alert = self.get_object()
        alert.mark_resolved(commit=True)
        return Response({"detail": "Alerta marcada como resuelta."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def snooze(self, request, pk=None):
        """
        Posponer una alerta. Puedes pasar un campo 'until' en el body
        para que la UI lo use (se guarda en payload['snoozed_until']).
        """
        alert = self.get_object()
        until = request.data.get("until") or timezone.now().isoformat()
        alert.snooze(until=until, commit=True)
        return Response({"detail": "Alerta pospuesta."}, status=status.HTTP_200_OK)
