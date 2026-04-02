from decimal import Decimal

from django.db import transaction as db_tx
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from finance.accounts.models.account import Account
from finance.transactions.Models.transacciones import (
    Transaction,
    Tag,
    IncomeSource,
    ScheduledPayment,
    TransactionParticipant,
)
from finance.transactions.Serializers.transactions_serializers import (
    TransactionSerializer,
    TagSerializer,
    IncomeSourceSerializer,
    ScheduledPaymentSerializer,
    TransactionParticipantSerializer,
)


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
            "payment_intent",
        )
        .prefetch_related("tags", "participants")
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
        "parent": ["exact"],
    }

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def reasignar_cuenta(self, request, pk=None):
        """
        Corrige una transacción mal asignada moviéndola a otra cuenta.
        Body: {"new_account_id": <id>}
        El rebalanceo real se hará vía accounts.signals (Account.recalc_balance).
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
        Flujo típico: ingest Open Finance -> pending -> usuario revisa -> posted.
        """
        tx = self.get_object()
        if tx.confirmed and tx.status in [
            Transaction.Status.POSTED,
            Transaction.Status.RECONCILED,
        ]:
            return Response(
                {"detail": "La transacción ya está confirmada."},
                status=status.HTTP_200_OK,
            )

        tx.confirmed = True
        if tx.status == Transaction.Status.PENDING:
            tx.status = Transaction.Status.POSTED
        tx.save(update_fields=["confirmed", "status"])

        return Response(
            {"detail": "Transacción marcada como confirmada."},
            status=status.HTTP_200_OK,
        )

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def add_comment(self, request, pk=None):
        """
        Añade un comentario tipo hilo a la transacción.
        Body: {"text": "Pagué esto por Ana, me dio efectivo"}
        """
        tx = self.get_object()
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response(
                {"detail": "El campo 'text' es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comments = list(tx.comments or [])
        comments.append(
            {
                "author_id": request.user.id,
                "text": text,
                "created_at": timezone.now().isoformat(),
            }
        )
        tx.comments = comments
        tx.save(update_fields=["comments"])

        return Response(
            {"detail": "Comentario agregado."},
            status=status.HTTP_201_CREATED,
        )

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def registrar_reembolso(self, request, pk=None):
        """
        Registra un ingreso de reembolso para un gasto marcado como reembolsable.
        Body opcional:
        {
          "amount": 120000,        # si se omite, usa el total del gasto
          "date": "2025-01-10",    # si se omite, hoy
          "notes": "Reembolso Ana"
        }
        """
        expense = self.get_object()

        if expense.type != Transaction.Type.EXPENSE:
            return Response(
                {"detail": "Solo puedes registrar reembolsos sobre gastos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not expense.is_reimbursable:
            return Response(
                {
                    "detail": (
                        "Esta transacción no está marcada como reembolsable. "
                        "Activa 'is_reimbursable' si quieres rastrear el reembolso."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if expense.reimbursed:
            return Response(
                {"detail": "Este gasto ya está marcado como reembolsado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_amount = request.data.get("amount")
        amount = Decimal(str(raw_amount)) if raw_amount is not None else expense.amount

        raw_date = request.data.get("date")
        dt = parse_date(raw_date) if raw_date else timezone.now().date()

        notes = request.data.get("notes") or f"Reembolso de gasto #{expense.id}"

        payload = {
            "type": Transaction.Type.INCOME,
            "status": Transaction.Status.POSTED,
            "amount": amount,
            "date": dt,
            "account": expense.account.id,
            "category": None,
            "vendor": expense.vendor.id if expense.vendor_id else None,
            "source": "reimbursement",
            "notes": notes,
        }

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        income_tx = serializer.save(owner=request.user)

        expense.reimbursed = True
        expense.reimbursement_transaction = income_tx
        expense.save(update_fields=["reimbursed", "reimbursement_transaction"])

        return Response(
            {
                "detail": "Reembolso registrado.",
                "reimbursement_transaction_id": income_tx.id,
            },
            status=status.HTTP_201_CREATED,
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
        Genera una Transaction contable a partir de un ScheduledPayment pendiente.

        Este flujo representa materializacion local del ledger, no la ejecucion
        de un rail externo. El gating de pagos embebidos vive en
        `payments.payment_intents`, que sera el punto de entrada para retailers,
        PSPs o integradores externos.
        """
        sp = self.get_object()

        if sp.status == ScheduledPayment.Status.PAID:
            return Response(
                {"detail": "Este pago programado ya está marcado como pagado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tx = Transaction.objects.create(
            owner=sp.owner,
            type=Transaction.Type.EXPENSE,
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

        tx.tags.set(sp.tags.all())

        sp.status = ScheduledPayment.Status.PAID
        sp.save(update_fields=["status"])

        return Response(
            {
                "detail": "Transacción generada a partir del pago programado.",
                "transaction_id": tx.id,
            },
            status=status.HTTP_201_CREATED,
        )


class TransactionParticipantViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = (
        TransactionParticipant.objects.select_related("transaction")
        .all()
    )
    serializer_class = TransactionParticipantSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ["display_name", "email", "phone"]
    ordering_fields = ["created_at", "share_amount", "pending_amount"]
    filterset_fields = {
        "transaction": ["exact"],
        "status": ["exact"],
        "invite_status": ["exact"],
    }
