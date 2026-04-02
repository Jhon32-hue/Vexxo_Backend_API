"""
ViewSet de observabilidad y soporte del outbox de cuentas.

Descripcion general:
- expone lectura del `DomainEventOutbox` filtrado por el alcance del usuario
- permite reintentar publicacion o liberar locks de eventos del dominio account

Analisis detallado:
- el outbox no es una tabla administrativa cualquiera; es parte de la
  confiabilidad transaccional del modulo financiero
- la API limita operaciones a eventos del aggregate `account` y solo para
  cuentas que el usuario puede ver
- las acciones mutables se reservan a usuarios con capacidad de administrar la
  cuenta asociada

Que se puede hacer despues:
- agregar un panel de salud agregado por status o tipo de evento
- enlazar eventos con auditoria, correlation_id y workers concretos
"""

from __future__ import annotations

from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from finance.accounts.models import Account, DomainEventOutbox
from finance.accounts.domain.events import get_account_event_catalog, get_account_event_governance, get_account_event_runtime
from finance.accounts.serializers import DomainEventOutboxSerializer, OutboxActionSerializer
from finance.accounts.services.event_service import publish_outbox_event
from finance.accounts.services.permission_service import account_scope_for_user, user_can_manage_account_settings
from support.audit.helpers import audit_log


class DomainEventOutboxViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API operativa del outbox transaccional de cuentas.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = DomainEventOutboxSerializer

    def get_queryset(self):
        scoped_accounts = account_scope_for_user(self.request.user, Account.objects.only("id"))
        scoped_ids = [str(account_id) for account_id in scoped_accounts.values_list("id", flat=True)]

        qs = DomainEventOutbox.objects.filter(aggregate_type="account", aggregate_id__in=scoped_ids)

        status_param = self.request.query_params.get("status")
        event_type = self.request.query_params.get("event_type")
        account_id = self.request.query_params.get("account")
        correlation_id = self.request.query_params.get("correlation_id")
        request_id = self.request.query_params.get("request_id")

        if status_param:
            qs = qs.filter(status=status_param)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if account_id:
            qs = qs.filter(aggregate_id=str(account_id))
        if correlation_id:
            qs = qs.filter(correlation_id=correlation_id)
        if request_id:
            qs = qs.filter(request_id=request_id)

        return qs.order_by("-occurred_at")

    def get_serializer_class(self):
        if self.action in {"publish_now", "retry", "release_lock"}:
            return OutboxActionSerializer
        return DomainEventOutboxSerializer

    def _linked_account(self, event: DomainEventOutbox) -> Account:
        if event.aggregate_type != "account":
            raise NotFound("El evento no pertenece al aggregate account.")
        try:
            return Account.objects.get(pk=int(event.aggregate_id))
        except (ValueError, TypeError, Account.DoesNotExist):
            raise NotFound("No se encontro la cuenta asociada al evento.")

    def _assert_can_manage_event(self, event: DomainEventOutbox) -> Account:
        account = self._linked_account(event)
        if not user_can_manage_account_settings(self.request.user, account):
            raise PermissionDenied("No puedes operar el outbox de esta cuenta.")
        return account

    def _audit(self, *, action_name: str, event: DomainEventOutbox, account: Account):
        audit_log(
            user=self.request.user,
            module="accounts",
            action=action_name,
            entity="DomainEventOutbox",
            entity_id=event.id,
            description=f"Operacion de outbox {action_name} para cuenta {account.id}",
            metadata={
                "account_id": account.id,
                "event_type": event.event_type,
                "status": event.status,
                "retry_count": event.retry_count,
            },
            silent=True,
        )

    @action(detail=True, methods=["post"])
    def publish_now(self, request, pk=None):
        event = self.get_object()
        account = self._assert_can_manage_event(event)

        if event.is_published:
            serializer = DomainEventOutboxSerializer(event, context=self.get_serializer_context())
            return Response(serializer.data, status=status.HTTP_200_OK)

        publish_outbox_event(event, publisher=f"api:{self.request.user.id}")
        event.refresh_from_db()
        self._audit(action_name="outbox_publish_now", event=event, account=account)
        serializer = DomainEventOutboxSerializer(event, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        event = self.get_object()
        account = self._assert_can_manage_event(event)

        if event.is_published:
            serializer = DomainEventOutboxSerializer(event, context=self.get_serializer_context())
            return Response(serializer.data, status=status.HTTP_200_OK)

        event.status = DomainEventOutbox.Status.PENDING
        event.next_attempt_at = None
        event.dead_lettered_at = None
        event.dead_letter_reason = ""
        event.last_backoff_seconds = 0
        event.release_lock(commit=False)
        event.save(
            update_fields=[
                "status",
                "next_attempt_at",
                "dead_lettered_at",
                "dead_letter_reason",
                "last_backoff_seconds",
                "locked_at",
                "locked_by",
            ]
        )
        publish_outbox_event(event, publisher=f"api:{self.request.user.id}")
        event.refresh_from_db()

        self._audit(action_name="outbox_retry", event=event, account=account)
        serializer = DomainEventOutboxSerializer(event, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def release_lock(self, request, pk=None):
        event = self.get_object()
        account = self._assert_can_manage_event(event)

        if not event.is_locked:
            raise ValidationError({"detail": "El evento no tiene lock activo."})

        event.release_lock()
        event.refresh_from_db()
        self._audit(action_name="outbox_release_lock", event=event, account=account)
        serializer = DomainEventOutboxSerializer(event, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def health(self, request):
        qs = self.get_queryset()
        by_status = list(qs.values("status").annotate(total=Count("id")).order_by("status"))
        by_event_type = list(qs.values("event_type").annotate(total=Count("id")).order_by("event_type"))
        by_result = list(qs.values("last_publish_result").annotate(total=Count("id")).order_by("last_publish_result"))
        return Response(
            {
                "total_events": qs.count(),
                "by_status": by_status,
                "by_event_type": by_event_type,
                "by_result": by_result,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def contracts(self, request):
        return Response(
            {
                "runtime": get_account_event_runtime(),
                "governance": get_account_event_governance(),
                "events": get_account_event_catalog(),
            },
            status=status.HTTP_200_OK,
        )
