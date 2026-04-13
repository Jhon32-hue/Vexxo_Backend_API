from django.utils import timezone
from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from alerts.alerts.ai_services import enrich_alert_with_ai
from alerts.alerts.models.alerts import Alert, AlertStatus
from alerts.alerts.serializers.alert_serializers import AlertaSerializer
from common.internal_auth import assert_internal_token


class AlertaViewSet(viewsets.ModelViewSet):
    """
    API de alertas de Vexxo_app.

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


class AlertAiWorkerView(views.APIView):
    """
    Endpoint interno para workers de IA.

    Puede vivir detras del mismo servicio o de un Cloud Run interno dedicado.
    La autenticacion es por token interno o por OIDC a nivel infraestructura.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        try:
            assert_internal_token(
                request,
                "ALERTS_AI_INTERNAL_TOKEN",
                detail="Unauthorized",
            )
        except Exception as exc:
            if hasattr(exc, "detail"):
                return Response({"detail": str(exc.detail)}, status=status.HTTP_403_FORBIDDEN)
            raise

        alert_id = request.data.get("alert_id")
        if not alert_id:
            return Response({"detail": "alert_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        alert = Alert.objects.filter(pk=alert_id).first()
        if alert is None:
            return Response({"detail": "Alert no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        enrich_alert_with_ai(
            alert,
            correlation_id=request.data.get("correlation_id"),
        )
        return Response(
            {
                "detail": "Alert enriched.",
                "alert_id": str(alert.pk),
            },
            status=status.HTTP_200_OK,
        )
