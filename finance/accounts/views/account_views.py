"""
ViewSet principal de cuentas financieras.

Descripcion general:
- expone CRUD controlado y acciones de dominio para `Account`
- concentra filtros, trazabilidad y transiciones operativas de una cuenta

Analisis detallado:
- `Account` no es un recurso plano; mezcla identidad financiera, integracion,
  consolidacion multimoneda, reglas de gasto y colaboracion
- por eso las transiciones importantes se modelan como acciones explicitas:
  recalcular balance, congelar, archivar, cerrar o marcar principal
- el queryset usa el scope social del usuario para que cuentas propias y
  compartidas vivan en el mismo flujo REST sin mezclar permisos

Que se puede hacer despues:
- agregar endpoints de dashboards mas especializados sobre la misma base
- separar version mobile/publica si Vexxo necesita contratos mas delgados
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from finance.accounts.domain.guards import get_account_plan_snapshot, primary_account_limit_errors
from finance.accounts.domain.events import (
    AccountDomainEventTypes,
    build_account_lifecycle_payload,
    build_account_sync_payload,
    get_account_event_catalog,
    get_account_event_governance,
    get_account_event_runtime,
)
from finance.accounts.models import Account, AccountStatus
from finance.accounts.serializers import (
    AccountDetailSerializer,
    AccountExternalLinkSerializer,
    AccountMembershipSerializer,
    AccountPlanUsageSerializer,
    AccountReasonActionSerializer,
    AccountRecalcSerializer,
    AccountSyncErrorSerializer,
    AccountSyncRunningSerializer,
    AccountSyncScheduleSerializer,
    AccountSyncSuccessSerializer,
    AccountSummarySerializer,
    AccountWriteSerializer,
)
from finance.accounts.services.outbox_service import (
    publish_account_balance_updated,
    publish_account_event,
    publish_account_lifecycle_event,
    publish_account_sync_event,
)
from finance.accounts.services.permission_service import (
    account_scope_for_user,
    user_can_manage_account_settings,
)
from support.audit.helpers import audit_log

ZERO = Decimal("0.00")


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "si"}


def _is_false(value: str | None) -> bool:
    return (value or "").strip().lower() in {"0", "false", "no"}


class AccountViewSet(viewsets.ModelViewSet):
    """
    API avanzada de cuentas para Vexxo.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AccountDetailSerializer

    def get_queryset(self):
        user = self.request.user
        qs = account_scope_for_user(
            user,
            Account.objects.select_related("owner", "shared_from_user").all(),
        ).prefetch_related("memberships__user")

        qs = qs.annotate(
            total_transactions=Count("transactions", distinct=True),
            active_memberships_count=Count(
                "memberships",
                filter=Q(memberships__is_active=True),
                distinct=True,
            ),
        )

        account_type = self.request.query_params.get("type")
        currency = self.request.query_params.get("currency")
        ownership = self.request.query_params.get("ownership")
        role = self.request.query_params.get("role")
        visibility = self.request.query_params.get("visibility")
        status_param = self.request.query_params.get("status")
        provider = self.request.query_params.get("provider")
        institution = self.request.query_params.get("institution")
        sync_status = self.request.query_params.get("sync_status")
        sync_health = self.request.query_params.get("sync_health")
        external_link = self.request.query_params.get("external_link")
        primary_param = self.request.query_params.get("is_primary")
        search = self.request.query_params.get("search")
        mine_param = self.request.query_params.get("mine")
        shared_param = self.request.query_params.get("shared")
        active_param = self.request.query_params.get("active")
        archived_param = self.request.query_params.get("archived")
        include_closed = self.request.query_params.get("include_closed")
        order_by = self.request.query_params.get("order_by")

        if account_type:
            qs = qs.filter(type=account_type)
        if currency:
            qs = qs.filter(currency=currency)
        if ownership:
            qs = qs.filter(ownership=ownership)
        if role:
            qs = qs.filter(role=role)
        if visibility:
            qs = qs.filter(visibility=visibility)
        if provider:
            qs = qs.filter(provider=provider)
        if institution:
            qs = qs.filter(institution__icontains=institution)
        if sync_status:
            qs = qs.filter(sync_status=sync_status)
        if external_link is not None:
            if _is_true(external_link):
                qs = qs.exclude(provider="").exclude(external_id="")
            elif _is_false(external_link):
                qs = qs.filter(provider="", external_id="")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(institution__icontains=search))

        if _is_true(mine_param):
            qs = qs.filter(owner=user)
        elif _is_true(shared_param):
            qs = qs.exclude(owner=user)

        if primary_param is not None:
            qs = qs.filter(is_primary=_is_true(primary_param))

        if status_param:
            qs = qs.filter(status=status_param)
        elif active_param is not None:
            if _is_true(active_param):
                qs = qs.filter(status=AccountStatus.ACTIVE)
            elif _is_false(active_param):
                qs = qs.exclude(status=AccountStatus.ACTIVE)
        elif not _is_true(include_closed):
            qs = qs.exclude(status=AccountStatus.CLOSED)

        if archived_param is not None:
            archived_filter = Q(status=AccountStatus.ARCHIVED) | Q(archived=True)
            if _is_true(archived_param):
                qs = qs.filter(archived_filter)
            elif _is_false(archived_param):
                qs = qs.exclude(archived_filter)

        if sync_health:
            health_filters = {
                "disconnected": Q(provider="") | Q(external_id=""),
                "error": Q(sync_status="error") & ~Q(provider="") & ~Q(external_id=""),
                "stale": Q(sync_status="stale") & ~Q(provider="") & ~Q(external_id=""),
                "syncing": Q(sync_status="running") & ~Q(provider="") & ~Q(external_id=""),
                "healthy": Q(sync_status="ok") & ~Q(provider="") & ~Q(external_id=""),
                "idle": Q(sync_status="idle") & ~Q(provider="") & ~Q(external_id=""),
            }
            if sync_health in health_filters:
                qs = qs.filter(health_filters[sync_health])

        allowed_order = {
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
            "name",
            "-name",
            "balance",
            "-balance",
        }
        qs = qs.distinct()
        if order_by in allowed_order:
            return qs.order_by(order_by)
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return AccountWriteSerializer
        if self.action == "link_external_source":
            return AccountExternalLinkSerializer
        if self.action == "mark_sync_running":
            return AccountSyncRunningSerializer
        if self.action == "mark_sync_success":
            return AccountSyncSuccessSerializer
        if self.action == "mark_sync_error":
            return AccountSyncErrorSerializer
        if self.action == "schedule_sync":
            return AccountSyncScheduleSerializer
        if self.action in {"freeze", "archive", "unarchive", "close_account"}:
            return AccountReasonActionSerializer
        if self.action == "recalc_balance":
            return AccountRecalcSerializer
        if self.action == "plan_usage":
            return AccountPlanUsageSerializer
        return AccountDetailSerializer

    def _assert_can_manage_account(self, account: Account) -> None:
        if not user_can_manage_account_settings(self.request.user, account):
            raise PermissionDenied("No puedes administrar esta cuenta.")

    def _audit(self, *, action_name: str, account: Account, description: str, metadata: dict | None = None):
        audit_log(
            user=self.request.user,
            module="accounts",
            action=action_name,
            entity="Account",
            entity_id=account.id,
            description=description,
            metadata=metadata or {},
            silent=True,
        )

    @transaction.atomic
    def perform_create(self, serializer):
        account = serializer.save(owner=self.request.user)
        account.ensure_owner_membership()
        self._audit(
            action_name="create",
            account=account,
            description=f"Cuenta creada: {account.name}",
            metadata={
                "type": account.type,
                "currency": account.currency,
                "ownership": account.ownership,
            },
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_CREATED,
            payload=build_account_lifecycle_payload(account=account, change="created"),
            metadata={"source": "accounts.views.perform_create"},
        )

    @transaction.atomic
    def perform_update(self, serializer):
        account = self.get_object()
        self._assert_can_manage_account(account)

        before = {
            "name": account.name,
            "type": account.type,
            "currency": account.currency,
            "status": account.status,
            "ownership": account.ownership,
            "visibility": account.visibility,
            "balance": str(account.balance),
        }
        updated = serializer.save()
        after = {
            "name": updated.name,
            "type": updated.type,
            "currency": updated.currency,
            "status": updated.status,
            "ownership": updated.ownership,
            "visibility": updated.visibility,
            "balance": str(updated.balance),
        }
        self._audit(
            action_name="update",
            account=updated,
            description=f"Cuenta actualizada: {updated.name}",
            metadata={"before": before, "after": after},
        )
        publish_account_lifecycle_event(
            account=updated,
            event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
            payload=build_account_lifecycle_payload(
                account=updated,
                change="updated",
                before=before,
                after=after,
            ),
            metadata={"source": "accounts.views.perform_update"},
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        self._assert_can_manage_account(instance)
        if instance.balance != ZERO:
            raise ValidationError(
                {"detail": "No puedes cerrar una cuenta con saldo distinto de cero desde DELETE."}
            )

        instance.close(commit=True, reason="deleted_from_api")
        self._audit(
            action_name="soft_delete",
            account=instance,
            description=f"Cuenta cerrada via DELETE: {instance.name}",
            metadata={"final_balance": str(instance.balance)},
        )
        publish_account_lifecycle_event(
            account=instance,
            event_type=AccountDomainEventTypes.ACCOUNT_CLOSED,
            payload=build_account_lifecycle_payload(
                account=instance,
                change="deleted_from_api",
                extra={"final_balance": str(instance.balance), "reason": "deleted_from_api"},
            ),
            metadata={"source": "accounts.views.perform_destroy"},
        )

    @action(detail=True, methods=["post"])
    def set_primary(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        if account.status != AccountStatus.ACTIVE:
            raise ValidationError({"detail": "Solo una cuenta activa puede marcarse como principal."})

        limit_errors = primary_account_limit_errors(account.owner, exclude_account_id=account.pk)
        if limit_errors:
            raise ValidationError(limit_errors)

        account.set_as_primary()
        self._audit(
            action_name="set_primary",
            account=account,
            description=f"Cuenta marcada como principal: {account.name}",
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="set_primary",
                extra={"is_primary": True},
            ),
            metadata={"source": "accounts.views.set_primary"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_PRIMARY_CHANGED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="primary_changed",
                extra={"is_primary": True},
            ),
            metadata={"source": "accounts.views.set_primary"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def recalc_balance(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        old_balance = account.balance
        new_balance = account.recalc_balance(
            reason=serializer.validated_data.get("reason") or "manual_recalc",
        )
        publish_account_balance_updated(
            account=account,
            old_balance=old_balance,
            new_balance=new_balance,
            reason=serializer.validated_data.get("reason") or "manual_recalc",
            metadata={"source": "accounts.views.recalc_balance"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_RECALCULATED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="recalculated",
                extra={
                    "old_balance": str(old_balance),
                    "new_balance": str(new_balance),
                    "reason": serializer.validated_data.get("reason") or "manual_recalc",
                },
            ),
            metadata={"source": "accounts.views.recalc_balance"},
        )
        self._audit(
            action_name="recalc_balance",
            account=account,
            description=f"Recalculo manual de balance: {account.name}",
            metadata={"old_balance": str(old_balance), "new_balance": str(new_balance)},
        )
        return Response(
            {
                "message": "Balance recalculado correctamente.",
                "old_balance": str(old_balance),
                "new_balance": str(new_balance),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def freeze(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if account.status == AccountStatus.CLOSED:
            raise ValidationError({"detail": "No puedes congelar una cuenta cerrada."})

        reason = serializer.validated_data.get("reason", "")
        account.freeze(reason=reason)
        self._audit(
            action_name="freeze",
            account=account,
            description=f"Cuenta congelada: {account.name}",
            metadata={"reason": reason},
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="freeze",
                extra={"reason": reason},
            ),
            metadata={"source": "accounts.views.freeze"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_FROZEN,
            payload=build_account_lifecycle_payload(
                account=account,
                change="frozen",
                extra={"reason": reason},
            ),
            metadata={"source": "accounts.views.freeze"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def unfreeze(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        account.unfreeze()
        self._audit(
            action_name="unfreeze",
            account=account,
            description=f"Cuenta descongelada: {account.name}",
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
            payload=build_account_lifecycle_payload(account=account, change="unfreeze"),
            metadata={"source": "accounts.views.unfreeze"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_UNFROZEN,
            payload=build_account_lifecycle_payload(account=account, change="unfrozen"),
            metadata={"source": "accounts.views.unfreeze"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data.get("reason", "")
        account.archive()
        self._audit(
            action_name="archive",
            account=account,
            description=f"Cuenta archivada: {account.name}",
            metadata={"reason": reason},
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="archive",
                extra={"reason": reason},
            ),
            metadata={"source": "accounts.views.archive"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_ARCHIVED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="archived",
                extra={"reason": reason},
            ),
            metadata={"source": "accounts.views.archive"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def unarchive(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        account.unarchive()
        self._audit(
            action_name="unarchive",
            account=account,
            description=f"Cuenta desarchivada: {account.name}",
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_UPDATED,
            payload=build_account_lifecycle_payload(account=account, change="unarchive"),
            metadata={"source": "accounts.views.unarchive"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_UNARCHIVED,
            payload=build_account_lifecycle_payload(account=account, change="unarchived"),
            metadata={"source": "accounts.views.unarchive"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def close_account(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if account.is_closed:
            return Response(
                {"detail": "La cuenta ya estaba cerrada.", "final_balance": str(account.balance)},
                status=status.HTTP_200_OK,
            )

        if account.balance != ZERO:
            raise ValidationError(
                {"detail": "No puedes cerrar una cuenta con saldo distinto de cero."}
            )

        reason = serializer.validated_data.get("reason", "")
        final_balance = account.close(reason=reason)
        self._audit(
            action_name="close",
            account=account,
            description=f"Cuenta cerrada: {account.name}",
            metadata={"final_balance": str(final_balance), "reason": reason},
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_CLOSED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="closed",
                extra={"final_balance": str(final_balance), "reason": reason},
            ),
            metadata={"source": "accounts.views.close_account"},
        )
        return Response(
            {"message": "Cuenta cerrada correctamente.", "final_balance": str(final_balance)},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        summary = self.get_queryset().values("type", "currency", "status").annotate(
            total_accounts=Count("id"),
            total_balance=Sum("balance"),
        )
        serializer = AccountSummarySerializer(summary, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        account = self.get_object()
        memberships = account.memberships.select_related("user", "invited_by").order_by("-is_active", "user__username")

        active_param = request.query_params.get("active")
        if active_param is not None:
            if _is_true(active_param):
                memberships = memberships.filter(is_active=True)
            elif _is_false(active_param):
                memberships = memberships.filter(is_active=False)

        serializer = AccountMembershipSerializer(
            memberships,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def link_external_source(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account.link_external_account(**serializer.validated_data)
        self._audit(
            action_name="link_external_source",
            account=account,
            description=f"Cuenta vinculada a proveedor externo: {account.name}",
            metadata={
                "provider": account.provider,
                "external_id": account.external_id,
            },
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_EXTERNAL_LINKED,
            payload=build_account_sync_payload(
                account=account,
                change="link_external_source",
            ),
            metadata={"source": "accounts.views.link_external_source"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def unlink_external_source(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        previous = {"provider": account.provider, "external_id": account.external_id}
        account.unlink_external_account(clear_metadata=False)
        self._audit(
            action_name="unlink_external_source",
            account=account,
            description=f"Cuenta desvinculada de proveedor externo: {account.name}",
            metadata=previous,
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_EXTERNAL_UNLINKED,
            payload=build_account_lifecycle_payload(
                account=account,
                change="unlink_external_source",
                extra={"previous": previous},
            ),
            metadata={"source": "accounts.views.unlink_external_source"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def schedule_sync(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "Debes vincular la cuenta a un proveedor externo antes de programar sync."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        next_sync_at = account.schedule_next_sync(**serializer.validated_data)
        self._audit(
            action_name="schedule_sync",
            account=account,
            description=f"Sync programado para cuenta: {account.name}",
            metadata={"next_sync_at": next_sync_at.isoformat()},
        )
        publish_account_lifecycle_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_SCHEDULED,
            payload=build_account_sync_payload(
                account=account,
                change="schedule_sync",
                extra={"next_sync_at": next_sync_at.isoformat()},
            ),
            metadata={"source": "accounts.views.schedule_sync"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def mark_sync_running(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "La cuenta no esta vinculada a un proveedor externo."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sync_cursor = serializer.validated_data.get("sync_cursor")
        next_sync_at = serializer.validated_data.get("next_sync_at")
        if sync_cursor is not None:
            account.sync_cursor = sync_cursor
        if next_sync_at is not None:
            account.next_sync_at = next_sync_at
        account.mark_sync_running(commit=False)
        account.save(update_fields=["sync_cursor", "next_sync_at", "sync_status", "last_sync_status_at", "updated_at"])

        self._audit(
            action_name="mark_sync_running",
            account=account,
            description=f"Sync en ejecucion para cuenta: {account.name}",
            metadata={"sync_cursor": account.sync_cursor, "next_sync_at": next_sync_at.isoformat() if next_sync_at else None},
        )
        publish_account_sync_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
            change="mark_sync_running",
            extra={"sync_cursor": account.sync_cursor},
            metadata={"source": "accounts.views.mark_sync_running"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STARTED,
            payload=build_account_sync_payload(
                account=account,
                change="sync_started",
                extra={"sync_cursor": account.sync_cursor},
            ),
            metadata={"source": "accounts.views.mark_sync_running"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def mark_sync_success(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "La cuenta no esta vinculada a un proveedor externo."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if "sync_cursor" in serializer.validated_data:
            account.sync_cursor = serializer.validated_data.get("sync_cursor") or ""
        if "provider_metadata" in serializer.validated_data:
            merged_metadata = dict(account.provider_metadata or {})
            merged_metadata.update(serializer.validated_data.get("provider_metadata") or {})
            account.provider_metadata = merged_metadata
        if serializer.validated_data.get("next_sync_at") is not None:
            account.next_sync_at = serializer.validated_data["next_sync_at"]

        account.mark_sync_ok(commit=False, duration_ms=serializer.validated_data.get("duration_ms", 0))
        account.save(
            update_fields=[
                "sync_status",
                "sync_error_message",
                "last_sync_at",
                "last_sync_status_at",
                "sync_attempts",
                "last_sync_duration_ms",
                "sync_cursor",
                "provider_metadata",
                "next_sync_at",
                "updated_at",
            ]
        )

        self._audit(
            action_name="mark_sync_success",
            account=account,
            description=f"Sync exitoso para cuenta: {account.name}",
            metadata={"duration_ms": account.last_sync_duration_ms, "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None},
        )
        publish_account_sync_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
            change="mark_sync_success",
            extra={"duration_ms": account.last_sync_duration_ms},
            metadata={"source": "accounts.views.mark_sync_success"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_SUCCEEDED,
            payload=build_account_sync_payload(
                account=account,
                change="sync_succeeded",
                extra={"duration_ms": account.last_sync_duration_ms},
            ),
            metadata={"source": "accounts.views.mark_sync_success"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def mark_sync_error(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "La cuenta no esta vinculada a un proveedor externo."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        next_sync_at = serializer.validated_data.get("next_sync_at")
        retry_in_minutes = serializer.validated_data.get("retry_in_minutes")
        account.mark_sync_error(message=serializer.validated_data["message"], commit=False)
        if next_sync_at is not None:
            account.next_sync_at = next_sync_at
        elif retry_in_minutes:
            account.schedule_next_sync(delay_minutes=retry_in_minutes, commit=False)
        account.save(update_fields=["sync_status", "sync_error_message", "last_sync_status_at", "sync_attempts", "next_sync_at", "updated_at"])

        self._audit(
            action_name="mark_sync_error",
            account=account,
            description=f"Sync con error para cuenta: {account.name}",
            metadata={"message": account.sync_error_message, "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None},
        )
        publish_account_sync_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
            change="mark_sync_error",
            extra={
                "message": account.sync_error_message,
                "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None,
            },
            metadata={"source": "accounts.views.mark_sync_error"},
        )
        publish_account_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_FAILED,
            payload=build_account_sync_payload(
                account=account,
                change="sync_failed",
                extra={
                    "message": account.sync_error_message,
                    "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None,
                },
            ),
            metadata={"source": "accounts.views.mark_sync_error"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def mark_sync_stale(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "La cuenta no esta vinculada a un proveedor externo."})

        account.mark_sync_stale()
        self._audit(
            action_name="mark_sync_stale",
            account=account,
            description=f"Cuenta marcada con sync stale: {account.name}",
        )
        publish_account_sync_event(
            account=account,
            event_type=AccountDomainEventTypes.ACCOUNT_SYNC_STATUS_CHANGED,
            change="mark_sync_stale",
            metadata={"source": "accounts.views.mark_sync_stale"},
        )
        return Response(AccountDetailSerializer(account, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def plan_usage(self, request):
        snapshot = get_account_plan_snapshot(request.user)
        serializer = self.get_serializer(snapshot)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def sync_overview(self, request):
        qs = self.get_queryset()
        with_external = qs.exclude(provider="").exclude(external_id="")
        summary = with_external.values("sync_status", "provider").annotate(
            total_accounts=Count("id"),
        ).order_by("provider", "sync_status")
        return Response(list(summary), status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def operational_overview(self, request):
        qs = self.get_queryset()
        with_external = qs.exclude(provider="").exclude(external_id="")
        return Response(
            {
                "totals": {
                    "accounts": qs.count(),
                    "active": qs.filter(status=AccountStatus.ACTIVE).count(),
                    "closed": qs.filter(status=AccountStatus.CLOSED).count(),
                    "archived": qs.filter(status=AccountStatus.ARCHIVED).count(),
                    "frozen": qs.filter(status=AccountStatus.FROZEN).count(),
                    "linked_external": with_external.count(),
                    "primary_accounts": qs.filter(is_primary=True).count(),
                    "shared_accounts": qs.exclude(owner=request.user).count(),
                },
                "by_status": list(qs.values("status").annotate(total=Count("id")).order_by("status")),
                "by_type": list(qs.values("type").annotate(total=Count("id")).order_by("type")),
                "by_currency": list(
                    qs.values("currency").annotate(total=Count("id"), total_balance=Sum("balance")).order_by("currency")
                ),
                "by_sync_status": list(
                    with_external.values("sync_status").annotate(total=Count("id")).order_by("sync_status")
                ),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def event_contract(self, request):
        return Response(
            {
                "module": "finance.accounts",
                "aggregate": "account",
                "runtime": get_account_event_runtime(),
                "governance": get_account_event_governance(),
                "events": get_account_event_catalog(),
            },
            status=status.HTTP_200_OK,
        )
