"""
Handlers HTTP del recurso `cuentas`.

Descripcion general:
- concentra las acciones REST del viewset principal y deja a `account_views.py`
  como fachada publica delgada

Analisis detallado:
- las vistas aqui validan permisos, coordinan serializers y delegan mutaciones
  de lifecycle/sync a servicios
- la idea es que el viewset orqueste y audite, no que contenga toda la logica
  de negocio ni todo el detalle de queries
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from finance.accounts.domain.guards import get_account_plan_snapshot
from finance.accounts.models import AccountStatus
from finance.accounts.serializers import AccountDetailSerializer, AccountMembershipSerializer, AccountSummarySerializer
from finance.accounts.services.account_lifecycle_service import (
    archive_account,
    close_account,
    close_account_from_delete,
    create_account,
    freeze_account,
    recalc_account_balance,
    set_account_primary,
    unarchive_account,
    unfreeze_account,
    update_account,
)
from finance.accounts.services.account_sync_service import (
    link_account_external_source,
    mark_account_sync_error,
    mark_account_sync_running,
    mark_account_sync_stale,
    mark_account_sync_success,
    schedule_account_sync,
    unlink_account_external_source,
)
from finance.accounts.services.account_policy_service import (
    validate_account_can_be_primary,
    validate_account_can_close,
    validate_account_external_link_allowed,
)
from finance.accounts.services.permission_service import user_can_manage_account_settings
from finance.accounts.views.account_query_builders import (
    build_account_detail_queryset,
    build_account_members_queryset,
    build_event_contract_payload,
    build_operational_overview_payload,
    build_summary_queryset,
    build_sync_overview_payload,
)
from support.audit.helpers import audit_log

ZERO = Decimal("0.00")


def assert_can_manage_account(*, acting_user, account) -> None:
    if not user_can_manage_account_settings(acting_user, account):
        raise PermissionDenied("No puedes administrar esta cuenta.")


def audit_account_action(*, acting_user, action_name: str, account, description: str, metadata: dict | None = None):
    audit_log(
        user=acting_user,
        module="accounts",
        action=action_name,
        entity="Account",
        entity_id=account.id,
        description=description,
        metadata=metadata or {},
        silent=True,
    )


class AccountActionHandlersMixin:
    def _assert_can_manage_account(self, account) -> None:
        assert_can_manage_account(acting_user=self.request.user, account=account)

    def _audit(self, *, action_name: str, account, description: str, metadata: dict | None = None):
        audit_account_action(
            acting_user=self.request.user,
            action_name=action_name,
            account=account,
            description=description,
            metadata=metadata,
        )

    def _account_detail_response(self, account, *, status_code=status.HTTP_200_OK):
        detailed_account = (
            build_account_detail_queryset(user=self.request.user, query_params=self.request.query_params)
            .filter(pk=account.pk)
            .first()
            or account
        )
        return Response(
            AccountDetailSerializer(detailed_account, context=self.get_serializer_context()).data,
            status=status_code,
        )

    @transaction.atomic
    def perform_create(self, serializer):
        account = serializer.save(owner=self.request.user)
        create_account(account)
        self._audit(
            action_name="create",
            account=account,
            description=f"Cuenta creada: {account.name}",
            metadata={"type": account.type, "currency": account.currency, "ownership": account.ownership},
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
            "provider": account.provider,
            "external_id": account.external_id,
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
            "provider": updated.provider,
            "external_id": updated.external_id,
            "ownership": updated.ownership,
            "visibility": updated.visibility,
            "balance": str(updated.balance),
        }
        update_account(account=updated, before=before, after=after)
        self._audit(
            action_name="update",
            account=updated,
            description=f"Cuenta actualizada: {updated.name}",
            metadata={"before": before, "after": after},
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        self._assert_can_manage_account(instance)
        validate_account_can_close(instance, via_delete=True)

        close_account_from_delete(instance)
        self._audit(
            action_name="soft_delete",
            account=instance,
            description=f"Cuenta cerrada via DELETE: {instance.name}",
            metadata={"final_balance": str(instance.balance)},
        )

    @action(detail=True, methods=["post"])
    def set_primary(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        validate_account_can_be_primary(account)

        set_account_primary(account)
        self._audit(action_name="set_primary", account=account, description=f"Cuenta marcada como principal: {account.name}")
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def recalc_balance(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason") or "manual_recalc"

        result = recalc_account_balance(account=account, reason=reason)
        self._audit(
            action_name="recalc_balance",
            account=account,
            description=f"Recalculo manual de balance: {account.name}",
            metadata={"old_balance": str(result["old_balance"]), "new_balance": str(result["new_balance"])},
        )
        return Response(
            {
                "message": "Balance recalculado correctamente.",
                "old_balance": str(result["old_balance"]),
                "new_balance": str(result["new_balance"]),
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
        freeze_account(account=account, reason=reason)
        self._audit(
            action_name="freeze",
            account=account,
            description=f"Cuenta congelada: {account.name}",
            metadata={"reason": reason},
        )
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def unfreeze(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        unfreeze_account(account)
        self._audit(action_name="unfreeze", account=account, description=f"Cuenta descongelada: {account.name}")
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        archive_account(account=account, reason=reason)
        self._audit(
            action_name="archive",
            account=account,
            description=f"Cuenta archivada: {account.name}",
            metadata={"reason": reason},
        )
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def unarchive(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        unarchive_account(account)
        self._audit(action_name="unarchive", account=account, description=f"Cuenta desarchivada: {account.name}")
        return self._account_detail_response(account)

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
        validate_account_can_close(account)

        reason = serializer.validated_data.get("reason", "")
        final_balance = close_account(account=account, reason=reason)
        self._audit(
            action_name="close",
            account=account,
            description=f"Cuenta cerrada: {account.name}",
            metadata={"final_balance": str(final_balance), "reason": reason},
        )
        return Response(
            {"message": "Cuenta cerrada correctamente.", "final_balance": str(final_balance)},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        serializer = AccountSummarySerializer(build_summary_queryset(queryset=self.get_queryset()), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        account = self.get_object()
        memberships = build_account_members_queryset(account=account, query_params=request.query_params)
        serializer = AccountMembershipSerializer(memberships, many=True, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def link_external_source(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        validate_account_external_link_allowed(account=account)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link_account_external_source(account=account, data=serializer.validated_data)

        self._audit(
            action_name="link_external_source",
            account=account,
            description=f"Cuenta vinculada a proveedor externo: {account.name}",
            metadata={"provider": account.provider, "external_id": account.external_id},
        )
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def unlink_external_source(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)

        previous = unlink_account_external_source(account)
        self._audit(
            action_name="unlink_external_source",
            account=account,
            description=f"Cuenta desvinculada de proveedor externo: {account.name}",
            metadata=previous,
        )
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def schedule_sync(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "Debes vincular la cuenta a un proveedor externo antes de programar sync."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_sync_at = schedule_account_sync(account=account, data=serializer.validated_data)

        self._audit(
            action_name="schedule_sync",
            account=account,
            description=f"Sync programado para cuenta: {account.name}",
            metadata={"next_sync_at": next_sync_at.isoformat()},
        )
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def mark_sync_running(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "La cuenta no esta vinculada a un proveedor externo."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mark_account_sync_running(account=account, data=serializer.validated_data)

        next_sync_at = serializer.validated_data.get("next_sync_at")
        self._audit(
            action_name="mark_sync_running",
            account=account,
            description=f"Sync en ejecucion para cuenta: {account.name}",
            metadata={"sync_cursor": account.sync_cursor, "next_sync_at": next_sync_at.isoformat() if next_sync_at else None},
        )
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def mark_sync_success(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "La cuenta no esta vinculada a un proveedor externo."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mark_account_sync_success(account=account, data=serializer.validated_data)

        self._audit(
            action_name="mark_sync_success",
            account=account,
            description=f"Sync exitoso para cuenta: {account.name}",
            metadata={
                "duration_ms": account.last_sync_duration_ms,
                "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None,
            },
        )
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def mark_sync_error(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "La cuenta no esta vinculada a un proveedor externo."})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mark_account_sync_error(account=account, data=serializer.validated_data)

        self._audit(
            action_name="mark_sync_error",
            account=account,
            description=f"Sync con error para cuenta: {account.name}",
            metadata={
                "message": account.sync_error_message,
                "next_sync_at": account.next_sync_at.isoformat() if account.next_sync_at else None,
            },
        )
        return self._account_detail_response(account)

    @action(detail=True, methods=["post"])
    def mark_sync_stale(self, request, pk=None):
        account = self.get_object()
        self._assert_can_manage_account(account)
        if not account.has_external_link:
            raise ValidationError({"detail": "La cuenta no esta vinculada a un proveedor externo."})

        mark_account_sync_stale(account)
        self._audit(
            action_name="mark_sync_stale",
            account=account,
            description=f"Cuenta marcada con sync stale: {account.name}",
        )
        return self._account_detail_response(account)

    @action(detail=False, methods=["get"])
    def plan_usage(self, request):
        snapshot = get_account_plan_snapshot(request.user)
        serializer = self.get_serializer(snapshot)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def sync_overview(self, request):
        return Response(build_sync_overview_payload(queryset=self.get_queryset()), status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def operational_overview(self, request):
        payload = build_operational_overview_payload(queryset=self.get_queryset(), user=request.user)
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def event_contract(self, request):
        return Response(build_event_contract_payload(), status=status.HTTP_200_OK)
