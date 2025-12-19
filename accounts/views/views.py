from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.models.account import Account
from accounts.serializers.serializador import AccountSerializer
from django.db.models import Sum


class AccountViewSet(viewsets.ModelViewSet):
    """
    API avanzada para gestión de cuentas.
    Incluye balance, cierre, resumen y transacciones relacionadas.
    """
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Account.objects.filter(owner=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # ----------------------------------------------------------
    # EXTRA ACTIONS
    # ----------------------------------------------------------

    @action(detail=True, methods=["post"])
    def recalc_balance(self, request, pk=None):
        """Recalcula y sincroniza el balance con las transacciones confirmadas."""
        account = self.get_object()
        new_balance = account.recalc_balance()
        return Response(
            {"message": f"Balance recalculado: {new_balance}", "balance": new_balance},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def close_account(self, request, pk=None):
        """Cierra una cuenta (no permite más transacciones)."""
        account = self.get_object()
        final_balance = account.close()
        return Response(
            {"message": "Cuenta cerrada correctamente.", "final_balance": final_balance},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Devuelve un resumen agregado por tipo de cuenta."""
        qs = self.get_queryset()
        summary = qs.values("type", "currency").annotate(
            total_balance=Sum("balance"), total_accounts=Account ("id")
        )
        return Response(summary, status=status.HTTP_200_OK)
