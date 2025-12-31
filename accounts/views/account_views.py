from decimal import Decimal

from django.db.models import Count, Sum, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from accounts.models.account import Account
from accounts.serializers.account_serializador import AccountSerializer
from audit.helpers import audit_log


class AccountViewSet(viewsets.ModelViewSet):
    """
    API avanzada para gestión de cuentas de Mindwallet.

    - CRUD de cuentas propiedad del usuario autenticado.
    - Acciones de negocio: recalcular balance, cerrar cuenta.
    - Endpoint de resumen para dashboards (Summary360 / WealthFlow).
    """

    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]

    # ========= QUERYSET BASE =========

    def get_queryset(self):
        user = self.request.user
        qs = Account.objects.filter(owner=user)

        # Filtros opcionales por query params
        account_type = self.request.query_params.get("type")       # p.ej. bank, cash...
        active_param = self.request.query_params.get("active")     # "true" / "false"
        currency = self.request.query_params.get("currency")       # COP, USD, EUR...
        search = self.request.query_params.get("search")           # fragmento del nombre
        include_closed = self.request.query_params.get("include_closed")

        if account_type:
            qs = qs.filter(type=account_type)

        if currency:
            qs = qs.filter(currency=currency)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(institution__icontains=search)
            )

        # Si el cliente envía ?active=..., respetamos eso
        if active_param is not None:
            if active_param.lower() == "true":
                qs = qs.filter(is_active=True)
            elif active_param.lower() == "false":
                qs = qs.filter(is_active=False)
        else:
            # Si NO hay active en los params:
            #   - por defecto ocultamos cuentas cerradas,
            #   - salvo que include_closed=true
            show_closed = include_closed and include_closed.lower() == "true"
            if not show_closed:
                qs = qs.filter(is_active=True)

        # Anotamos total_transactions para evitar N+1 en el serializer
        # Ajusta "transactions" al related_name real del FK en Transaction
        qs = qs.annotate(total_transactions=Count("transactions"))

        return qs.order_by("-created_at")

    # ========= HOOKS CRUD =========

    def perform_create(self, serializer):
        account = serializer.save(owner=self.request.user)

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
                "plan_snapshot": getattr(
                    getattr(self.request.user, "settings", None),
                    "plan",
                    "free",
                ),
            },
        )

    def perform_update(self, serializer):
        before = self.get_object()
        before_snapshot = {
            "name": before.name,
            "type": before.type,
            "currency": before.currency,
            "initial_balance": str(before.initial_balance),
            "is_active": before.is_active,
            "is_primary": before.is_primary,
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
                },
            },
        )

    def perform_destroy(self, instance):
        """
        Soft delete:
        - No eliminamos físicamente la cuenta.
        - La marcamos como cerrada e inactiva.
        - Mantenemos histórico y ledger.

        Regla fuerte: solo permitimos "eliminar" si el saldo es 0.00,
        para no romper la consistencia contable.
        """
        final_balance = instance.balance

        if final_balance != Decimal("0.00"):
            raise ValidationError(
                {
                    "detail": (
                        "No puedes eliminar una cuenta con saldo distinto de cero. "
                        "Primero ajusta el saldo o ciérrala correctamente."
                    )
                }
            )

        # Usamos el método close del modelo para centralizar la lógica
        instance.close(commit=True)

        audit_log(
            user=self.request.user,
            module="accounts",
            action="soft_delete",
            entity="Account",
            entity_id=instance.id,
            description=f"Cuenta desactivada (soft delete): {instance.name}",
            metadata={
                "final_balance": str(final_balance),
            },
        )
        # Importante: NO llamamos a super().perform_destroy(instance)
        # para no borrar la fila de la base de datos.

    # ========= EXTRA ACTIONS =========

    @action(detail=True, methods=["post"])
    def recalc_balance(self, request, pk=None):
        """
        Fuerza el recálculo del balance de la cuenta a partir del ledger.
        Útil si hubo ajustes manuales o importaciones masivas."""
        account = self.get_object()
        old_balance = account.balance
        new_balance = account.recalc_balance()

        audit_log(
            user=request.user,
            module="accounts",
            action="recalc_balance",
            entity="Account",
            entity_id=account.id,
            description="Recalculo de balance desde API",
            metadata={
                "old_balance": str(old_balance),
                "new_balance": str(new_balance),
            },
        )

        return Response(
            {
                "message": "Balance recalculado correctamente.",
                "old_balance": old_balance,
                "new_balance": new_balance,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def close_account(self, request, pk=None):
        """
        Cierra la cuenta si cumple las reglas de negocio.
        Regla fuerte: solo se puede cerrar si el saldo es 0.00.
        """
        account = self.get_object()

        if account.is_closed:
            return Response(
                {
                    "detail": "La cuenta ya estaba cerrada.",
                    "final_balance": account.balance,
                },
                status=status.HTTP_200_OK,
            )

        if account.balance != Decimal("0.00"):
            return Response(
                {
                    "detail": "No puedes cerrar una cuenta con saldo distinto de cero.",
                    "balance": account.balance,
                },
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
            metadata={
                "final_balance": str(final_balance),
            },
        )

        return Response(
            {
                "message": "Cuenta cerrada correctamente.",
            "final_balance": final_balance,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        Resumen agregado de cuentas por tipo y moneda.
        Ideal para Summary360 / WealthFlow.

        Devuelve algo como:
        [
          {"type": "bank", "currency": "COP", "total_balance": 1500000, "total_accounts": 2},
          ...
        ]
        """
        qs = self.get_queryset()  # ya viene filtrado por usuario y activos (según params)

        summary = qs.values("type", "currency").annotate(
            total_balance=Sum("balance"),
            total_accounts=Count("id"),
        )

        return Response(summary, status=status.HTTP_200_OK)
