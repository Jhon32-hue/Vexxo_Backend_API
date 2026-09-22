"""
API de inbox persistente para notificaciones del sistema.

Descripcion general:
- expone las notificaciones persistidas en `notifications.deliveries`
- permite a la UI listar, inspeccionar y marcar como leidas las entregas

Analisis detallado:
- este modulo vuelve operacional la persistencia creada por listeners de
  dominio: ya no basta con guardar filas, ahora la app puede consumirlas
- el alcance es deliberadamente simple: inbox in-app, lectura, filtros basicos
  y marcado de lectura
"""

from __future__ import annotations

from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime

from notifications.deliveries.models import NotificationDelivery, NotificationStatus


class NotificationDeliverySerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = NotificationDelivery
        fields = [
            "id",
            "channel",
            "status",
            "event_type",
            "source",
            "title",
            "message",
            "payload",
            "dedupe_key",
            "is_read",
            "delivered_at",
            "read_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class NotificationDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationDeliverySerializer

    def get_queryset(self):
        qs = NotificationDelivery.objects.filter(owner=self.request.user).order_by("-created_at")

        status_value = (self.request.query_params.get("status") or "").strip()
        channel = (self.request.query_params.get("channel") or "").strip()
        event_type = (self.request.query_params.get("event_type") or "").strip()
        unread = (self.request.query_params.get("unread") or "").strip().lower()
        created_after = (self.request.query_params.get("created_after") or "").strip()

        if status_value:
            qs = qs.filter(status=status_value)
        if channel:
            qs = qs.filter(channel=channel)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if unread in {"1", "true", "yes"}:
            qs = qs.exclude(status=NotificationStatus.READ)
        if created_after:
            parsed = parse_datetime(created_after)
            if parsed is not None:
                qs = qs.filter(created_at__gt=parsed)
        return qs

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_read()
        return Response(self.get_serializer(notification).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        notifications = list(self.get_queryset().exclude(status=NotificationStatus.READ)[:500])
        for notification in notifications:
            notification.mark_read()
        return Response({"marked": len(notifications)}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.get_queryset()
        return Response(
            {
                "total": qs.count(),
                "unread": qs.exclude(status=NotificationStatus.READ).count(),
                "read": qs.filter(status=NotificationStatus.READ).count(),
            },
            status=status.HTTP_200_OK,
        )
