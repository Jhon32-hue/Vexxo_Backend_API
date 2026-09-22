"""
Modelos de planificacion de pagos.

No ejecutan el rail externo. Modelan el "quiero repetir / programar" para que
despues una corrida genere un `PaymentIntent`.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from finance.budgets.attribution import BudgetAttributionSource, BudgetScope


class PaymentTemplate(models.Model):
    class PaymentType(models.TextChoices):
        BILL = "bill", "Bill"
        TRANSFER = "transfer", "Transfer"
        FRIEND = "friend", "Friend"
        INVOICE = "invoice", "Invoice"
        OTHER = "other", "Other"

    class AmountMode(models.TextChoices):
        FIXED = "fixed", "Fixed"
        VARIABLE = "variable", "Variable"

    class Cadence(models.TextChoices):
        ONCE = "once", "Once"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        BIMONTHLY = "bimonthly", "Bimonthly"
        QUARTERLY = "quarterly", "Quarterly"
        YEARLY = "yearly", "Yearly"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_templates",
    )
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_templates",
    )
    category = models.ForeignKey(
        "categories.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_templates",
    )
    budget_scope = models.CharField(
        max_length=16,
        choices=BudgetScope.choices,
        blank=True,
        default="",
    )
    shared_budget = models.ForeignKey(
        "budgets.SharedBudget",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_templates",
    )
    budget_attribution_source = models.CharField(
        max_length=32,
        choices=BudgetAttributionSource.choices,
        blank=True,
        default="",
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_templates",
    )
    debt = models.ForeignKey(
        "debts.Debt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_templates",
    )
    installment = models.ForeignKey(
        "debts.DebtInstallment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_templates",
    )
    name = models.CharField(max_length=160)
    payment_type = models.CharField(max_length=24, choices=PaymentType.choices, default=PaymentType.OTHER)
    amount_mode = models.CharField(max_length=16, choices=AmountMode.choices, default=AmountMode.FIXED)
    default_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=12, default="COP")
    cadence = models.CharField(max_length=24, choices=Cadence.choices, default=Cadence.MONTHLY)
    interval_count = models.PositiveIntegerField(default=1)
    beneficiary_name = models.CharField(max_length=160, blank=True, default="")
    beneficiary_document = models.CharField(max_length=64, blank=True, default="")
    beneficiary_account_ref = models.CharField(max_length=128, blank=True, default="")
    external_reference = models.CharField(max_length=128, blank=True, default="")
    execution_defaults = models.JSONField(default=dict, blank=True)
    starts_at = models.DateField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    idempotency_key = models.CharField(max_length=160, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["next_run_at"]),
            models.Index(fields=["owner", "budget_scope", "is_active"]),
            models.Index(fields=["shared_budget", "next_run_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="payment_template_owner_idempotency_unique",
            )
        ]

    def clean(self):
        super().clean()
        if self.installment_id and not self.debt_id:
            self.debt_id = getattr(self.installment, "debt_id", None)
        if self.budget_scope == BudgetScope.SHARED and not self.shared_budget_id:
            raise ValidationError({"shared_budget": "Debes indicar un presupuesto compartido cuando budget_scope=shared."})
        if self.budget_scope in {"", BudgetScope.NONE, BudgetScope.PERSONAL} and self.shared_budget_id:
            raise ValidationError({"shared_budget": "shared_budget solo aplica cuando budget_scope=shared."})
        if self.debt_id and getattr(self.debt, "owner_id", None) not in (None, self.owner_id):
            raise ValidationError({"debt": "La deuda debe pertenecer al mismo owner del pago programado."})
        if self.installment_id:
            installment_owner_id = getattr(self.installment, "owner_id", None)
            if installment_owner_id not in (None, self.owner_id):
                raise ValidationError({"installment": "La cuota debe pertenecer al mismo owner del pago programado."})
            if self.debt_id and getattr(self.installment, "debt_id", None) not in (None, self.debt_id):
                raise ValidationError({"installment": "La cuota no pertenece a la deuda seleccionada."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class PaymentScheduleRun(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        DUE = "due", "Due"
        OVERDUE = "overdue", "Overdue"
        PROCESSING = "processing", "Processing"
        PAID = "paid", "Paid"
        PAID_OUTSIDE_VEXXO = "paid_outside_vexxo", "Paid outside Vexxo"
        POSTPONED = "postponed", "Postponed"
        SKIPPED = "skipped", "Skipped"
        CANCELED = "canceled", "Canceled"
        FAILED = "failed", "Failed"

    class ResolutionAction(models.TextChoices):
        MARK_PAID = "mark_paid", "Mark paid"
        PAID_OUTSIDE_VEXXO = "paid_outside_vexxo", "Paid outside Vexxo"
        POSTPONE = "postpone", "Postpone"
        SKIP = "skip", "Skip"
        CANCEL = "cancel", "Cancel"
        PAY_WITH_VEXXO = "pay_with_vexxo", "Pay with Vexxo"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_schedule_runs",
    )
    template = models.ForeignKey(
        PaymentTemplate,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    payment_intent = models.ForeignKey(
        "payment_intents.PaymentIntent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedule_runs",
    )
    materialized_transaction = models.ForeignKey(
        "transactions.Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_schedule_runs",
    )
    scheduled_for = models.DateTimeField()
    due_on = models.DateField(null=True, blank=True)
    expected_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    expected_currency = models.CharField(max_length=12, default="COP")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SCHEDULED)
    reminder_stage = models.PositiveSmallIntegerField(default=0)
    reminder_count = models.PositiveSmallIntegerField(default=0)
    last_reminded_at = models.DateTimeField(null=True, blank=True)
    postponed_until = models.DateField(null=True, blank=True)
    paid_at = models.DateField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_action = models.CharField(max_length=32, choices=ResolutionAction.choices, blank=True, default="")
    resolution_note = models.TextField(blank=True, default="")
    idempotency_key = models.CharField(max_length=160, unique=True)
    run_payload = models.JSONField(default=dict, blank=True)
    failure_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_for", "-id"]
        indexes = [
            models.Index(fields=["owner", "scheduled_for"]),
            models.Index(fields=["status", "scheduled_for"]),
            models.Index(fields=["owner", "status", "due_on"]),
        ]
