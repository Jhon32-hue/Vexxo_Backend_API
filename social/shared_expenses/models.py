from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from common.models.outbox import StandardDomainEventOutbox


class SharedExpense(models.Model):
    class SplitMethod(models.TextChoices):
        EQUAL = "equal", "Partes iguales"
        EXACT_AMOUNT = "exact_amount", "Montos exactos"
        PERCENTAGE = "percentage", "Porcentaje"
        WEIGHTED = "weighted", "Partes ponderadas"

    class Status(models.TextChoices):
        AWAITING_ACCEPTANCE = "awaiting_acceptance", "Esperando aceptacion"
        ACTIVE = "active", "Activo"
        PARTIALLY_SETTLED = "partially_settled", "Parcialmente liquidado"
        SETTLED = "settled", "Liquidado"
        CANCELED = "canceled", "Cancelado"
        DISPUTED = "disputed", "En disputa"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_shared_expenses")
    transaction = models.OneToOneField(
        "transactions.Transaction", on_delete=models.PROTECT, related_name="shared_expense"
    )
    team = models.ForeignKey(
        "teams.Team", null=True, blank=True, on_delete=models.SET_NULL, related_name="shared_expenses"
    )
    split_method = models.CharField(max_length=24, choices=SplitMethod.choices)
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.AWAITING_ACCEPTANCE, db_index=True
    )
    total_amount = models.DecimalField(max_digits=16, decimal_places=2)
    currency = models.CharField(max_length=3)
    version = models.PositiveIntegerField(default=1)
    idempotency_key = models.CharField(max_length=160)
    request_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["team", "status"]),
            models.Index(fields=["updated_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "idempotency_key"], name="uniq_shared_expense_owner_idempotency"
            ),
            models.CheckConstraint(condition=Q(total_amount__gt=0), name="shared_expense_total_positive"),
            models.CheckConstraint(condition=Q(version__gte=1), name="shared_expense_version_positive"),
        ]

    def clean(self):
        super().clean()
        if self.transaction_id and self.transaction.owner_id != self.owner_id:
            raise ValidationError({"transaction": "La transaccion debe pertenecer al pagador."})
        if self.transaction_id and self.transaction.type != self.transaction.Type.EXPENSE:
            raise ValidationError({"transaction": "Solo los gastos se pueden dividir."})

    def __str__(self) -> str:
        return f"shared-expense:{self.public_id}:{self.status}"


class SharedExpenseShare(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACCEPTED = "accepted", "Aceptada"
        PARTIALLY_SETTLED = "partially_settled", "Parcialmente liquidada"
        SETTLED = "settled", "Liquidada"
        CANCELED = "canceled", "Cancelada"
        DISPUTED = "disputed", "En disputa"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invitation_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    shared_expense = models.ForeignKey(SharedExpense, on_delete=models.CASCADE, related_name="shares")
    participant_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shared_expense_shares",
    )
    contact = models.ForeignKey(
        "contacts.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="shared_expense_shares"
    )
    transaction_participant = models.OneToOneField(
        "transactions.TransactionParticipant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shared_expense_share",
    )
    is_payer = models.BooleanField(default=False)
    display_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True, default="")
    expected_amount = models.DecimalField(max_digits=16, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    percentage = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    weight = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    accepted_at = models.DateTimeField(null=True, blank=True)
    disputed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["participant_user", "status"]),
            models.Index(fields=["email", "status"]),
            models.Index(fields=["shared_expense", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["shared_expense"], condition=Q(is_payer=True), name="uniq_shared_expense_payer_share"
            ),
            models.UniqueConstraint(
                fields=["shared_expense", "participant_user"],
                condition=Q(participant_user__isnull=False),
                name="uniq_shared_expense_participant_user",
            ),
            models.CheckConstraint(
                condition=Q(expected_amount__gt=0), name="shared_expense_share_expected_positive"
            ),
            models.CheckConstraint(
                condition=Q(paid_amount__gte=0), name="shared_expense_share_paid_non_negative"
            ),
        ]

    @property
    def pending_amount(self) -> Decimal:
        return max(Decimal("0.00"), self.expected_amount - self.paid_amount).quantize(Decimal("0.01"))

    def clean(self):
        super().clean()
        if self.paid_amount > self.expected_amount:
            raise ValidationError({"paid_amount": "El monto pagado excede la parte esperada."})
        if self.contact_id and self.contact.owner_id != self.shared_expense.owner_id:
            raise ValidationError({"contact": "El contacto no pertenece al pagador."})
        if self.is_payer and self.participant_user_id != self.shared_expense.owner_id:
            raise ValidationError({"participant_user": "La parte del pagador debe pertenecer al owner."})

    def __str__(self) -> str:
        return f"share:{self.public_id}:{self.expected_amount}"


class SharedExpenseSettlement(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmada"
        REVERSED = "reversed", "Revertida"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    shared_expense = models.ForeignKey(SharedExpense, on_delete=models.PROTECT, related_name="settlements")
    share = models.ForeignKey(SharedExpenseShare, on_delete=models.PROTECT, related_name="settlements")
    transaction = models.OneToOneField(
        "transactions.Transaction", on_delete=models.PROTECT, related_name="shared_expense_settlement"
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_shared_expense_settlements"
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CONFIRMED)
    idempotency_key = models.CharField(max_length=160)
    request_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["recorded_by", "idempotency_key"],
                name="uniq_shared_settlement_actor_idempotency",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="shared_expense_settlement_amount_positive"
            ),
        ]

    def clean(self):
        super().clean()
        if self.share_id and self.shared_expense_id != self.share.shared_expense_id:
            raise ValidationError({"share": "La parte no pertenece al gasto compartido."})
        if self.transaction_id and self.transaction_id == self.shared_expense.transaction_id:
            raise ValidationError({"transaction": "La liquidacion debe usar otra transaccion real."})


class SharedExpenseDomainEventOutbox(StandardDomainEventOutbox):
    class Meta(StandardDomainEventOutbox.Meta):
        verbose_name = "Shared expense domain event outbox"
        indexes = [
            models.Index(fields=["status", "occurred_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
        ]
