from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from finance.accounts.models.account import Account
from finance.accounts.models.membership import AccountMembership
from finance.accounts.serializers.account_serializers import AccountSerializer
from finance.accounts.services.permission_service import (
    account_scope_for_user,
    user_can_manage_members,
)
from finance.accounts.domain.enums import AccountMembershipRole
from support.audit.helpers import audit_log


ZERO = Decimal("0.00")


class AccountViewSet(viewsets.ModelViewSet):
    """
    API avanzada para gestión de cuentas.

    - CRUD con scope social (owner + memberships).
    - Acciones: recalc_balance, close_account, summary.
    - Soft delete como cierre contable.
    """

    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]

    # ========= QUERYSET BASE =========

    def get_queryset(self):
        user = self.request.user
        qs = account_scope_for_user(user, Account.objects.all())

        # -------- filtros opcionales por query params --------
        account_type = self.request.query_params.get("type")          # bank, cash...
        currency = self.request.query_params.get("currency")          # COP, USD...
        search = self.request.query_params.get("search")              # name / institution
        active_param = self.request.query_params.get("active")        # true/false
        include_closed = self.request.query_params.get("include_closed")
        archived_param = self.request.query_params.get("archived")    # true/false
        mine_param = self.request.query_params.get("mine")            # true -> solo owner
        shared_param = self.request.query_params.get("shared")        # true -> solo compartidas
        order_by = self.request.query_params.get("order_by")          # -created_at, name, -balance, etc.

        if account_type:
            qs = qs.filter(type=account_type)

        if currency:
            qs = qs.filter(currency=currency)

        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(institution__icontains=search))

        # mine/shared (útil para UX social)
        if mine_param and mine_param.lower() == "true":
            qs = qs.filter(owner=user)
        if shared_param and shared_param.lower() == "true":
            qs = qs.exclude(owner=user)

        # archived
        if archived_param is not None:
            if archived_param.lower() == "true":
                qs = qs.filter(archived=True)
            elif archived_param.lower() == "false":
                qs = qs.filter(archived=False)

        # active vs include_closed (tu lógica, pero más consistente)
        if active_param is not None:
            if active_param.lower() == "true":
                qs = qs.filter(is_active=True)
            elif active_param.lower() == "false":
                qs = qs.filter(is_active=False)
        else:
            show_closed = include_closed and include_closed.lower() == "true"
            if not show_closed:
                qs = qs.filter(is_active=True)

        # -------- performance / social --------
        # Evita N+1 si luego usas memberships en permisos/serializer/acciones
        qs = qs.prefetch_related("memberships")

        # OJO: ajusta "transactions" al related_name real en Transaction
        # Si no existe, usa Count("transaction_set")
        qs = qs.annotate(total_transactions=Count("transactions", distinct=True))

        # El scope social usa JOIN => DISTINCT para que no duplique cuentas
        qs = qs.distinct()

        # orden
        allowed_order = {
            "created_at", "-created_at",
            "name", "-name",
            "balance", "-balance",
            "updated_at", "-updated_at",
        }
        if order_by in allowed_order:
            return qs.order_by(order_by)
        return qs.order_by("-created_at")

    # ========= PERMISSION HELPERS =========

    def _membership_for_user(self, account: Account):
        """
        Devuelve membership activo del usuario o None.
        """
        user = self.request.user
        return account.memberships.filter(user=user, is_active=True).first()

    def _assert_can_manage_account(self, account: Account) -> None:
        """
        Regla:
        - Owner puede.
        - Si no es owner: necesita can_manage_account_settings o ser admin/owner por rol.
        """
        user = self.request.user
        if account.owner_id == user.id:
            return

        membership = self._membership_for_user(account)
        if not membership:
            raise ValidationError({"detail": "No tienes permisos sobre esta cuenta."})

        if getattr(membership, "can_manage_account_settings", False):
            return

        # fallback por rol/peso (tu servicio ya lo decide)
        if user_can_manage_members(user, account):
            return

        raise ValidationError({"detail": "No puedes modificar esta cuenta compartida."})

    # ========= HOOKS CRUD =========

    @transaction.atomic
    def perform_create(self, serializer):
        """
        Crea cuenta + garantiza membership OWNER.
        Atomic para evitar estado raro si algo falla a mitad.
        """
        account = serializer.save(owner=self.request.user)

        AccountMembership.objects.get_or_create(
            account=account,
            user=self.request.user,
            defaults={
                "role": AccountMembershipRole.OWNER,
                "can_post_transactions": True,
                "can_manage_members": True,
                "can_manage_account_settings": True,
                "can_view_analytics": True,
            },
        )

        audit_log(
            user=self.request.user,
            module="accounts",
            action="create",
            entity="Account",
            entity_id=account.id,
            description=f"Cuenta creada: {account.name}",
            metadata={
                "type": account.type,
                "currency": account.currency,
                "initial_balance": str(account.initial_balance),
                "plan_snapshot": getattr(getattr(self.request.user, "settings", None), "plan", "free"),
            },
        )

    @transaction.atomic
    def perform_update(self, serializer):
        before = self.get_object()
        self._assert_can_manage_account(before)

        before_snapshot = {
            "name": before.name,
            "type": before.type,
            "currency": before.currency,
            "initial_balance": str(before.initial_balance),
            "is_active": before.is_active,
            "is_primary": before.is_primary,
            "archived": before.archived,
        }

        account = serializer.save()

        audit_log(
            user=self.request.user,
            module="accounts",
            action="update",
            entity="Account",
            entity_id=account.id,
            description=f"Cuenta actualizada: {account.name}",
            metadata={
                "before": before_snapshot,
                "after": {
                    "name": account.name,
                    "type": account.type,
                    "currency": account.currency,
                    "initial_balance": str(account.initial_balance),
                    "is_active": account.is_active,
                    "is_primary": account.is_primary,
                    "archived": account.archived,
                },
            },
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        """
        Soft delete (cierre contable):
        - NO borra DB.
        - Cierra la cuenta.
        - Regla fuerte: balance debe ser 0.00
        """
        self._assert_can_manage_account(instance)
        final_balance = instance.balance

        if final_balance != ZERO:
            raise ValidationError(
                {
                    "detail": (
                        "No puedes eliminar una cuenta con saldo distinto de cero. "
                        "Primero ajusta el saldo o ciérrala correctamente."
                    )
                }
            )

        instance.close(commit=True)

        audit_log(
            user=self.request.user,
            module="accounts",
            action="soft_delete",
            entity="Account",
            entity_id=instance.id,
            description=f"Cuenta desactivada (soft delete): {instance.name}",
            metadata={"final_balance": str(final_balance)},
        )

    # ========= EXTRA ACTIONS =========

    @action(detail=True, methods=["post"])
    def recalc_balance(self, request, pk=None):
        """
        Fuerza recálculo desde ledger (debug/soporte/reconciliación manual).
        """
        account = self.get_object()
        self._assert_can_manage_account(account)

        old_balance = account.balance
        new_balance = account.recalc_balance()

        audit_log(
            user=request.user,
            module="accounts",
            action="recalc_balance",
            entity="Account",
            entity_id=account.id,
            description="Recalculo de balance desde API",
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
    def close_account(self, request, pk=None):
        """
        Cierra la cuenta (regla fuerte: balance 0).
        """
        account = self.get_object()
        self._assert_can_manage_account(account)

        if account.is_closed:
            return Response(
                {"detail": "La cuenta ya estaba cerrada.", "final_balance": str(account.balance)},
                status=status.HTTP_200_OK,
            )

        if account.balance != ZERO:
            return Response(
                {"detail": "No puedes cerrar una cuenta con saldo distinto de cero.", "balance": str(account.balance)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        final_balance = account.close()

        audit_log(
            user=request.user,
            module="accounts",
            action="close",
            entity="Account",
            entity_id=account.id,
            description=f"Cuenta cerrada: {account.name}",
            metadata={"final_balance": str(final_balance)},
        )

        return Response(
            {"message": "Cuenta cerrada correctamente.", "final_balance": str(final_balance)},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        Resumen agregado por type+currency para dashboards.
        Respeta filtros del get_queryset().
        """
        qs = self.get_queryset()

        summary = qs.values("type", "currency").annotate(
            total_balance=Sum("balance"),
            total_accounts=Count("id"),
        )

        return Response(summary, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        """
        Bonus social: lista miembros de la cuenta (solo lectura).
        """
        account = self.get_object()
        # si está en queryset, ya pasa scope social
        members = account.memberships.filter(is_active=True).values(
            "user_id", "role", "access_mode",
            "can_post_transactions", "can_manage_members",
            "can_manage_account_settings", "can_view_analytics",
            "joined_at", "revoked_at",
        )
        return Response(list(members), status=status.HTTP_200_OK)
