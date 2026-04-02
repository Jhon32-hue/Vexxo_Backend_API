"""
Modelos de planificacion de pagos.

No ejecutan el rail externo. Modelan el "quiero repetir / programar" para que
despues una corrida genere un `PaymentIntent`.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


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
    legacy_scheduled_payment = models.OneToOneField(
        "transactions.ScheduledPayment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_template",
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
    vendor = models.ForeignKey(
        "vendors.Vendor",
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["next_run_at"]),
        ]


class PaymentScheduleRun(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

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
    scheduled_for = models.DateTimeField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.REQUESTED)
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
        ]
