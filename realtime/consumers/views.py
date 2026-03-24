"""
API de consulta de senales realtime persistidas.

Descripcion general:
- expone `RealtimeSignal` como feed tecnico para polling o debug operativo
- permite a frontend y soporte inspeccionar las senales emitidas al usuario

Analisis detallado:
- `RealtimeSignal` no intenta ser un inbox funcional ni un stream durable de
  negocio; es un rastro liviano de cambios relevantes para superficies
  interactivas
- esta API sirve tanto para UX como para observabilidad de bajo costo
"""

from __future__ import annotations

from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from realtime.consumers.models import RealtimeSignal


class RealtimeSignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = RealtimeSignal
        fields = [
            "id",
            "owner_id",
            "channel",
            "event",
            "aggregate_type",
            "aggregate_id",
            "payload",
            "published_at",
            "created_at",
        ]
        read_only_fields = fields


class RealtimeSignalViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RealtimeSignalSerializer

    def get_queryset(self):
        qs = RealtimeSignal.objects.filter(owner_id=self.request.user.id).order_by("-created_at")

        channel = (self.request.query_params.get("channel") or "").strip()
        event = (self.request.query_params.get("event") or "").strip()
        aggregate_type = (self.request.query_params.get("aggregate_type") or "").strip()
        aggregate_id = (self.request.query_params.get("aggregate_id") or "").strip()
        since_id = (self.request.query_params.get("since_id") or "").strip()

        if channel:
            qs = qs.filter(channel=channel)
        if event:
            qs = qs.filter(event=event)
        if aggregate_type:
            qs = qs.filter(aggregate_type=aggregate_type)
        if aggregate_id:
            qs = qs.filter(aggregate_id=aggregate_id)
        if since_id.isdigit():
            qs = qs.filter(pk__gt=int(since_id))
        return qs

    @action(detail=False, methods=["get"])
    def latest(self, request):
        signal = self.get_queryset().first()
        if signal is None:
            return Response({}, status=status.HTTP_204_NO_CONTENT)
        return Response(self.get_serializer(signal).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.get_queryset()
        return Response(
            {
                "total": qs.count(),
                "channels": sorted({item for item in qs.values_list("channel", flat=True).distinct()}),
                "events": sorted({item for item in qs.values_list("event", flat=True).distinct()}),
            },
            status=status.HTTP_200_OK,
        )
