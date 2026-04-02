"""
ViewSet operativo para `AccountBalanceFallback`.

Descripcion general:
- expone lectura y agregados de salud sobre degradaciones del balance
  incremental

Analisis detallado:
- esta API permite soporte, observabilidad y producto detectar cuando el cache
  de balance debio recalcularse desde ledger
- no muta la tabla; solo permite consulta filtrada sobre cuentas visibles para
  el usuario autenticado
"""

from __future__ import annotations

from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from finance.accounts.models import Account, AccountBalanceFallback
from finance.accounts.serializers import AccountBalanceFallbackSerializer
from finance.accounts.services.permission_service import account_scope_for_user
from finance.accounts.views.account_query_builders import is_false, is_true


class AccountBalanceFallbackViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AccountBalanceFallbackSerializer

    def get_queryset(self):
        scoped_accounts = account_scope_for_user(self.request.user, Account.objects.only("id"))
        qs = AccountBalanceFallback.objects.select_related("account", "account__owner").filter(account__in=scoped_accounts)

        account_id = self.request.query_params.get("account")
        reason = self.request.query_params.get("reason")
        source = self.request.query_params.get("source")
        transaction_id = self.request.query_params.get("transaction_id")
        recalculated = self.request.query_params.get("recalculated")

        if account_id:
            qs = qs.filter(account_id=account_id)
        if reason:
            qs = qs.filter(reason=reason)
        if source:
            qs = qs.filter(source=source)
        if transaction_id:
            qs = qs.filter(transaction_id=str(transaction_id))
        if recalculated is not None:
            if is_true(recalculated):
                qs = qs.filter(recalculated=True)
            elif is_false(recalculated):
                qs = qs.filter(recalculated=False)

        return qs.order_by("-created_at")

    @action(detail=False, methods=["get"])
    def health(self, request):
        qs = self.get_queryset()
        return Response(
            {
                "total_fallbacks": qs.count(),
                "by_reason": list(qs.values("reason").annotate(total=Count("id")).order_by("reason")),
                "by_source": list(qs.values("source").annotate(total=Count("id")).order_by("source")),
                "by_recalculated": list(
                    qs.values("recalculated").annotate(total=Count("id")).order_by("recalculated")
                ),
            },
            status=status.HTTP_200_OK,
        )
