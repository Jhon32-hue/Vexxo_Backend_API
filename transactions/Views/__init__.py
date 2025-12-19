# transactions/Views.py  (reemplaza tu archivo manteniendo import paths)

from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction as db_tx

from transactions.Models.transacciones import Transaction, Tag, IncomeSource, ScheduledPayment
from transactions.Serializers import (
    TransactionSerializer, TagSerializer, IncomeSourceSerializer, ScheduledPaymentSerializer
)

class OwnerScopedMixin:
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class TagViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = Tag.objects.all().order_by('name')
    serializer_class = TagSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["name"]

class IncomeSourceViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = IncomeSource.objects.all().order_by('name')
    serializer_class = IncomeSourceSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["name", "vendor__name"]

class TransactionViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related('account','category','vendor','debt','installment').all()
    serializer_class = TransactionSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ["notes", "vendor__name", "category__name"]
    ordering_fields = ["date", "amount", "created_at"]
    filterset_fields = {
        "type": ["exact"],
        "category": ["exact"],
        "vendor": ["exact"],
        "priority": ["exact"],
        "date": ["exact", "gte", "lte"],
        "confirmed": ["exact"],
        "tags": ["exact"],
    }

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def reasignar_cuenta(self, request, pk=None):
        """
        Corrige una transacción mal asignada moviéndola a otra cuenta.
        Body: {"new_account_id": <id>}
        """
        tx = self.get_object()
        new_account_id = request.data.get("new_account_id")
        if not new_account_id:
            return Response({"detail": "new_account_id es requerido."}, status=400)
        if str(tx.account_id) == str(new_account_id):
            return Response({"detail": "La cuenta nueva es la misma."}, status=400)

        from accounts.models import Account
        try:
            new_acc = Account.objects.get(pk=new_account_id, owner=request.user)
        except Account.DoesNotExist:
            return Response({"detail": "Cuenta no encontrada o no pertenece al usuario."}, status=404)

        # revertir efecto viejo y aplicar nuevo
        old_amount, old_account = tx.amount, tx.account
        tx.account = new_acc
        tx.save(update_fields=["account"])

        from transactions.utils_balance import apply_balance_effect
        apply_balance_effect(tx, old_amount=old_amount, old_account=old_account)
        return Response({"detail": "Transacción reasignada y balances actualizados."}, status=200)

class ScheduledPaymentViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = ScheduledPayment.objects.select_related('account','category','vendor','debt','installment').all()
    serializer_class = ScheduledPaymentSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ["name", "notes", "vendor__name"]
    ordering_fields = ["due_date", "amount", "created_at"]
    filterset_fields = {
        "status": ["exact"],
        "priority": ["exact"],
        "due_date": ["exact", "gte", "lte"],
        "debt": ["exact"],
        "installment": ["exact"],
    }
