# transactions/Views/transactions_views.py

from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction as db_tx

from transactions.Models.transacciones import (
    Transaction,
    Tag,
    IncomeSource,
    ScheduledPayment,
)
from transactions.Serializers.transactions_serializers import (
    TransactionSerializer,
    TagSerializer,
    IncomeSourceSerializer,
    ScheduledPaymentSerializer,
)
from accounts.models.account import Account


class OwnerScopedMixin:
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return super().get_queryset().filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class TagViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = Tag.objects.all().order_by("name")
    serializer_class = TagSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["name"]


class IncomeSourceViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = IncomeSource.objects.all().order_by("name")
    serializer_class = IncomeSourceSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["name", "vendor__name"]


class TransactionViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = (
        Transaction.objects.select_related(
            "account",
            "category",
            "vendor",
            "debt",
            "installment",
            "income_source",
            "scheduled_payment",
        )
        .prefetch_related("tags")
        .all()
    )
    serializer_class = TransactionSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ["notes", "vendor__name", "category__name"]
    ordering_fields = ["date", "amount", "created_at"]
    filterset_fields = {
        "type": ["exact"],
        "status": ["exact"],
        "category": ["exact"],
        "vendor": ["exact"],
        "priority": ["exact"],
        "date": ["exact", "gte", "lte"],
        "confirmed": ["exact"],
        "tags": ["exact"],
        "account": ["exact"],
    }

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def reasignar_cuenta(self, request, pk=None):
        """
        Corrige una transacción mal asignada moviéndola a otra cuenta.
        Body: {"new_account_id": <id>}

        El recálculo de balances se hará vía signals de accounts.
        """
        tx = self.get_object()
        new_account_id = request.data.get("new_account_id")

        if not new_account_id:
            return Response(
                {"detail": "new_account_id es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if str(tx.account_id) == str(new_account_id):
            return Response(
                {"detail": "La cuenta nueva es la misma."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            new_acc = Account.objects.get(pk=new_account_id, owner=request.user)
        except Account.DoesNotExist:
            return Response(
                {"detail": "Cuenta no encontrada o no pertenece al usuario."},
                status=status.HTTP_404_NOT_FOUND,
            )

        tx.account = new_acc
        tx.save(update_fields=["account"])

        return Response(
            {"detail": "Transacción reasignada. Los balances se han actualizado."},
            status=status.HTTP_200_OK,
        )

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def marcar_confirmada(self, request, pk=None):
        """
        Marca una transacción importada (pending/failed) como confirmada.
        Esto permite un flujo:
        - ingest desde Open Finance en estado pending
        - usuario revisa y confirma
        """
        tx = self.get_object()
        if tx.confirmed and tx.status in ["posted", "reconciled"]:
            return Response(
                {"detail": "La transacción ya está confirmada."},
                status=status.HTTP_200_OK,
            )

        tx.confirmed = True
        if tx.status == "pending":
            tx.status = "posted"
        tx.save(update_fields=["confirmed", "status"])

        return Response(
            {"detail": "Transacción marcada como confirmada."},
            status=status.HTTP_200_OK,
        )


class ScheduledPaymentViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = (
        ScheduledPayment.objects.select_related(
            "account",
            "category",
            "vendor",
            "debt",
            "installment",
        )
        .prefetch_related("tags")
        .all()
    )
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

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def generar_transaccion(self, request, pk=None):
        """
        Genera una Transaction a partir de un ScheduledPayment pendiente.
        Ideal para cuando el pago se ejecuta y quieres registrarlo en el ledger.
        """
        sp = self.get_object()

        if sp.status == ScheduledPayment.Status.PAID:
            return Response(
                {"detail": "Este pago programado ya está marcado como pagado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from transactions.Models.transacciones import Transaction

        tx = Transaction.objects.create(
            owner=sp.owner,
            type="expense",
            status=Transaction.Status.POSTED,
            amount=sp.amount,
            date=sp.due_date,
            account=sp.account,
            category=sp.category,
            vendor=sp.vendor,
            debt=sp.debt,
            installment=sp.installment,
            scheduled_payment=sp,
            source="scheduled_payment",
            notes=f"Pago programado: {sp.name}",
            confirmed=True,
        )

        # Relacionar tags del ScheduledPayment
        tx.tags.set(sp.tags.all())

        # Marcar pago programado como pagado (el signal también lo hace, pero aquí es explícito)
        sp.status = ScheduledPayment.Status.PAID
        sp.save(update_fields=["status"])

        return Response(
            {
                "detail": "Transacción generada a partir del pago programado.",
                "transaction_id": tx.id,
            },
            status=status.HTTP_201_CREATED,
        )
