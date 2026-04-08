from decimal import Decimal

from django.db import transaction as db_tx
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from finance.accounts.models.account import Account
from finance.accounts.services.permission_service import account_scope_for_user, user_can_post_transactions
from finance.transactions.actor_context import bind_transaction_actor
from finance.transactions.Models.transacciones import (
    IncomeSource,
    ScheduledPayment,
    Tag,
    Transaction,
    TransactionParticipant,
)
from finance.transactions.Serializers.transactions_serializers import (
    IncomeSourceSerializer,
    ScheduledPaymentSerializer,
    TagSerializer,
    TransactionParticipantSerializer,
    TransactionSerializer,
)
from finance.transactions.transaction_actions_service import (
    add_transaction_comment,
    confirm_transaction,
    materialize_transaction_from_legacy_scheduled_payment,
    reassign_transaction_account,
    register_transaction_reimbursement,
)
from finance.transactions.transaction_write_service import delete_transaction
from finance.transactions.transaction_validation_service import (
    participant_scope_for_user,
    scheduled_payment_scope_for_user,
    transaction_scope_for_user,
)


def _apply_temporal_filters(queryset, params, *, field_name: str):
    year = params.get("year")
    month = params.get("month")
    day = params.get("day")
    date_from = params.get("date_from")
    date_to = params.get("date_to")

    filters_to_apply = {}
    try:
        if year not in (None, ""):
            filters_to_apply[f"{field_name}__year"] = int(year)
        if month not in (None, ""):
            filters_to_apply[f"{field_name}__month"] = int(month)
        if day not in (None, ""):
            filters_to_apply[f"{field_name}__day"] = int(day)
    except (TypeError, ValueError):
        return queryset.none()
    if date_from:
        filters_to_apply[f"{field_name}__gte"] = parse_date(date_from) or date_from
    if date_to:
        filters_to_apply[f"{field_name}__lte"] = parse_date(date_to) or date_to
    if filters_to_apply:
        queryset = queryset.filter(**filters_to_apply)
    return queryset


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

    def get_queryset(self):
        queryset = transaction_scope_for_user(self.request.user, self.queryset)
        scope = (self.request.query_params.get("scope") or "all").strip().lower()
        if scope == "owned":
            queryset = queryset.filter(account__owner=self.request.user)
        elif scope == "shared":
            queryset = queryset.exclude(account__owner=self.request.user)
        return _apply_temporal_filters(queryset, self.request.query_params, field_name="date")

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        if not user_can_post_transactions(self.request.user, instance.account):
            raise PermissionDenied("No tienes permisos para eliminar transacciones en esta cuenta.")
        delete_transaction(instance=instance, actor=self.request.user)

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def reasignar_cuenta(self, request, pk=None):
        tx = self.get_object()
        new_account_id = request.data.get("new_account_id")
        if not new_account_id:
            return Response({"detail": "new_account_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if str(tx.account_id) == str(new_account_id):
            return Response({"detail": "La cuenta nueva es la misma."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            visible_accounts = account_scope_for_user(request.user, Account.objects.all())
            new_acc = visible_accounts.get(pk=new_account_id)
        except Account.DoesNotExist:
            return Response({"detail": "Cuenta no encontrada o sin acceso."}, status=status.HTTP_404_NOT_FOUND)
        if not user_can_post_transactions(request.user, new_acc):
            return Response({"detail": "No tienes permisos para mover transacciones a esta cuenta."}, status=status.HTTP_403_FORBIDDEN)
        with bind_transaction_actor(request.user):
            reassign_transaction_account(tx=tx, new_account=new_acc, actor=request.user)
        return Response({"detail": "Transaccion reasignada. Los balances se han actualizado."}, status=status.HTTP_200_OK)

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def marcar_confirmada(self, request, pk=None):
        tx = self.get_object()
        if not user_can_post_transactions(request.user, tx.account):
            return Response({"detail": "No tienes permisos para confirmar transacciones en esta cuenta."}, status=status.HTTP_403_FORBIDDEN)
        if tx.confirmed and tx.status in [Transaction.Status.POSTED, Transaction.Status.RECONCILED]:
            return Response({"detail": "La transaccion ya esta confirmada."}, status=status.HTTP_200_OK)
        with bind_transaction_actor(request.user):
            confirm_transaction(tx=tx, actor=request.user)
        return Response({"detail": "Transaccion marcada como confirmada."}, status=status.HTTP_200_OK)

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def add_comment(self, request, pk=None):
        tx = self.get_object()
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response({"detail": "El campo 'text' es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        with bind_transaction_actor(request.user):
            add_transaction_comment(tx=tx, text=text, actor=request.user)
        return Response({"detail": "Comentario agregado."}, status=status.HTTP_201_CREATED)

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def registrar_reembolso(self, request, pk=None):
        expense = self.get_object()
        if not user_can_post_transactions(request.user, expense.account):
            return Response({"detail": "No tienes permisos para registrar reembolsos en esta cuenta."}, status=status.HTTP_403_FORBIDDEN)
        if expense.type != Transaction.Type.EXPENSE:
            return Response({"detail": "Solo puedes registrar reembolsos sobre gastos."}, status=status.HTTP_400_BAD_REQUEST)
        if not expense.is_reimbursable:
            return Response(
                {"detail": "Esta transaccion no esta marcada como reembolsable. Activa 'is_reimbursable' si quieres rastrear el reembolso."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if expense.reimbursed:
            return Response({"detail": "Este gasto ya esta marcado como reembolsado."}, status=status.HTTP_400_BAD_REQUEST)
        raw_amount = request.data.get("amount")
        amount = Decimal(str(raw_amount)) if raw_amount is not None else expense.amount
        raw_date = request.data.get("date")
        dt = parse_date(raw_date) if raw_date else None
        notes = request.data.get("notes") or f"Reembolso de gasto #{expense.id}"
        with bind_transaction_actor(request.user):
            income_tx = register_transaction_reimbursement(
                expense=expense,
                amount=amount,
                date=dt,
                notes=notes,
                actor=request.user,
            )
        return Response(
            {"detail": "Reembolso registrado.", "reimbursement_transaction_id": income_tx.id},
            status=status.HTTP_201_CREATED,
        )


class ScheduledPaymentViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = (
        ScheduledPayment.objects.select_related("account", "category", "vendor", "debt", "installment")
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

    def get_queryset(self):
        queryset = scheduled_payment_scope_for_user(self.request.user, self.queryset)
        scope = (self.request.query_params.get("scope") or "all").strip().lower()
        if scope == "owned":
            queryset = queryset.filter(account__owner=self.request.user)
        elif scope == "shared":
            queryset = queryset.exclude(account__owner=self.request.user)
        return _apply_temporal_filters(queryset, self.request.query_params, field_name="due_date")

    def perform_create(self, serializer):
        account = serializer.validated_data.get("account")
        with bind_transaction_actor(self.request.user):
            serializer.save(owner=account.owner if account is not None else self.request.user)

    def perform_update(self, serializer):
        with bind_transaction_actor(self.request.user):
            serializer.save()

    def perform_destroy(self, instance):
        if instance.account and not user_can_post_transactions(self.request.user, instance.account):
            raise PermissionDenied("No tienes permisos para eliminar pagos programados en esta cuenta.")
        with bind_transaction_actor(self.request.user):
            super().perform_destroy(instance)

    @db_tx.atomic
    @action(detail=True, methods=["post"])
    def generar_transaccion(self, request, pk=None):
        sp = self.get_object()
        if sp.account and not user_can_post_transactions(request.user, sp.account):
            return Response({"detail": "No tienes permisos para generar transacciones en esta cuenta."}, status=status.HTTP_403_FORBIDDEN)
        if sp.status == ScheduledPayment.Status.PAID:
            return Response({"detail": "Este pago programado ya esta marcado como pagado."}, status=status.HTTP_400_BAD_REQUEST)
        with bind_transaction_actor(request.user):
            tx = materialize_transaction_from_legacy_scheduled_payment(scheduled_payment=sp)
        return Response(
            {
                "detail": "Transaccion generada a partir del pago programado.",
                "transaction_id": tx.id,
            },
            status=status.HTTP_201_CREATED,
        )


class TransactionParticipantViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = TransactionParticipant.objects.select_related("transaction", "contact").all()
    serializer_class = TransactionParticipantSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ["display_name", "email", "phone", "contact__name"]
    ordering_fields = ["created_at", "share_amount", "paid_amount"]
    filterset_fields = {
        "transaction": ["exact"],
        "contact": ["exact"],
        "direction": ["exact"],
        "status": ["exact"],
        "invite_status": ["exact"],
    }

    def get_queryset(self):
        queryset = participant_scope_for_user(self.request.user, self.queryset)
        scope = (self.request.query_params.get("scope") or "all").strip().lower()
        if scope == "owned":
            queryset = queryset.filter(transaction__account__owner=self.request.user)
        elif scope == "shared":
            queryset = queryset.exclude(transaction__account__owner=self.request.user)
        return _apply_temporal_filters(queryset, self.request.query_params, field_name="transaction__date")

    def perform_create(self, serializer):
        tx = serializer.validated_data.get("transaction")
        with bind_transaction_actor(self.request.user):
            serializer.save(owner=tx.owner if tx is not None else self.request.user)

    def perform_update(self, serializer):
        with bind_transaction_actor(self.request.user):
            serializer.save()

    def perform_destroy(self, instance):
        if not user_can_post_transactions(self.request.user, instance.transaction.account):
            raise PermissionDenied("No tienes permisos para modificar participantes de esta cuenta.")
        with bind_transaction_actor(self.request.user):
            super().perform_destroy(instance)

    @action(detail=False, methods=["get"])
    def by_contact(self, request):
        contact_id = request.query_params.get("contact_id")
        if not contact_id:
            return Response({"detail": "contact_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(self.get_queryset().filter(contact_id=contact_id), many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary_by_contact(self, request):
        from decimal import Decimal
        from django.db.models import Count, Q, Sum

        aggregates = (
            self.get_queryset()
            .filter(
                contact__isnull=False,
                status__in=[
                    TransactionParticipant.Status.ACTIVE,
                    TransactionParticipant.Status.PENDING,
                    TransactionParticipant.Status.PARTIAL,
                ],
            )
            .values("contact_id", "contact__name")
            .annotate(
                total_creditor=Sum("share_amount", filter=Q(direction="user_creditor")),
                total_debtor=Sum("share_amount", filter=Q(direction="user_debtor")),
                total_active=Count("id"),
            )
            .order_by("contact__name")
        )
        data = []
        for row in aggregates:
            total_creditor = Decimal(row["total_creditor"] or 0)
            total_debtor = Decimal(row["total_debtor"] or 0)
            net = (total_creditor - total_debtor).quantize(Decimal("0.01"))
            data.append(
                {
                    "contact_id": row["contact_id"],
                    "name": row["contact__name"],
                    "net_balance": net,
                    "total_active": row["total_active"],
                    "label": "Te debe" if net > 0 else "Debes" if net < 0 else "Liquidado",
                }
            )
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def mark_settled(self, request, pk=None):
        participant = self.get_object()
        if not user_can_post_transactions(request.user, participant.transaction.account):
            return Response({"detail": "No tienes permisos para liquidar participantes en esta cuenta."}, status=status.HTTP_403_FORBIDDEN)
        with bind_transaction_actor(request.user):
            participant.mark_settled()
        return Response(self.get_serializer(participant).data, status=status.HTTP_200_OK)
