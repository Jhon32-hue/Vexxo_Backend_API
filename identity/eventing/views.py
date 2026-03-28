"""
API operativa del outbox del bounded context identity.
"""

from __future__ import annotations

from django.db.models import Count
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from identity.eventing.models import IdentityDomainEventOutbox
from identity.eventing.serializers import IdentityDomainEventOutboxSerializer, IdentityOutboxActionSerializer
from identity.eventing.services import publish_identity_outbox_event
from identity.users.domain import get_user_event_catalog, get_user_event_governance, get_user_event_runtime


class IdentityDomainEventOutboxViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = IdentityDomainEventOutboxSerializer

    def get_queryset(self):
        qs = IdentityDomainEventOutbox.objects.all()
        status_param = self.request.query_params.get("status")
        event_type = self.request.query_params.get("event_type")
        aggregate_type = self.request.query_params.get("aggregate_type")
        aggregate_id = self.request.query_params.get("aggregate_id")
        if status_param:
            qs = qs.filter(status=status_param)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if aggregate_type:
            qs = qs.filter(aggregate_type=aggregate_type)
        if aggregate_id:
            qs = qs.filter(aggregate_id=str(aggregate_id))
        return qs.order_by("-occurred_at")

    def get_serializer_class(self):
        if self.action in {"publish_now", "retry", "release_lock"}:
            return IdentityOutboxActionSerializer
        return IdentityDomainEventOutboxSerializer

    @action(detail=True, methods=["post"])
    def publish_now(self, request, pk=None):
        event = self.get_object()
        if event.published_at:
            serializer = self.get_serializer(event)
            return Response(serializer.data, status=status.HTTP_200_OK)
        publish_identity_outbox_event(event)
        event.refresh_from_db()
        serializer = self.get_serializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        event = self.get_object()
        if event.published_at:
            serializer = self.get_serializer(event)
            return Response(serializer.data, status=status.HTTP_200_OK)
        event.status = IdentityDomainEventOutbox.Status.PENDING
        event.release_lock(commit=False)
        event.save(update_fields=["status", "locked_at", "locked_by"])
        publish_identity_outbox_event(event)
        event.refresh_from_db()
        serializer = self.get_serializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def release_lock(self, request, pk=None):
        event = self.get_object()
        if not event.locked_at:
            raise ValidationError({"detail": "El evento no tiene lock activo."})
        event.release_lock()
        event.refresh_from_db()
        serializer = self.get_serializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def health(self, request):
        qs = self.get_queryset()
        return Response(
            {
                "total_events": qs.count(),
                "by_status": list(qs.values("status").annotate(total=Count("id")).order_by("status")),
                "by_event_type": list(qs.values("event_type").annotate(total=Count("id")).order_by("event_type")),
                "locked_events": qs.exclude(locked_at__isnull=True).count(),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def contracts(self, request):
        return Response(
            {
                "runtime": get_user_event_runtime(),
                "governance": get_user_event_governance(),
                "events": get_user_event_catalog(),
            },
            status=status.HTTP_200_OK,
        )
