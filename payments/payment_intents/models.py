"""
Modelo canonico para intents de pago embebido.

No representa el ledger final. Representa la intencion operativa de enviar un
comando a un PSP/retailer externo y recibir callbacks posteriores.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class PaymentIntent(models.Model):
    class PaymentType(models.TextChoices):
        BILL = "bill", "Bill"
        TRANSFER = "transfer", "Transfer"
        FRIEND = "friend", "Friend"
        INVOICE = "invoice", "Invoice"
        RECURRING = "recurring", "Recurring"
        SCHEDULED = "scheduled", "Scheduled"
        PAYOUT = "payout", "Payout"
        OTHER = "other", "Other"

    class Rail(models.TextChoices):
        PSE = "pse", "PSE"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        WALLET = "wallet", "Wallet"
        CARD = "card", "Card"
        CASH = "cash", "Cash"
        PAYOUT = "payout", "Payout"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        DISPATCHED = "dispatched", "Dispatched"
        PROCESSING = "processing", "Processing"
        REQUIRES_ACTION = "requires_action", "Requires action"
        SUCCEEDED = "succeeded", "Succeeded"
        SETTLED = "settled", "Settled"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_intents",
    )
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )
    category = models.ForeignKey(
        "categories.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_intents",
    )
    payment_type = models.CharField(max_length=24, choices=PaymentType.choices, default=PaymentType.OTHER)
    rail = models.CharField(max_length=24, choices=Rail.choices, default=Rail.OTHER)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=12, default="COP")
    provider = models.CharField(max_length=64)
    internal_reference = models.CharField(max_length=128, blank=True, default="")
    external_reference = models.CharField(max_length=128, blank=True, default="")
    invoice_reference = models.CharField(max_length=128, blank=True, default="")
    provider_intent_id = models.CharField(max_length=128, blank=True, default="")
    provider_reference = models.CharField(max_length=128, blank=True, default="")
    provider_cus = models.CharField(max_length=64, blank=True, default="")
    beneficiary_name = models.CharField(max_length=160, blank=True, default="")
    beneficiary_document = models.CharField(max_length=64, blank=True, default="")
    beneficiary_account_ref = models.CharField(max_length=128, blank=True, default="")
    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATED)
    source = models.CharField(max_length=64, blank=True, default="payments.payment_intents.create")
    command_payload = models.JSONField(default=dict, blank=True)
    destination_payload = models.JSONField(default=dict, blank=True)
    pricing_snapshot = models.JSONField(default=dict, blank=True)
    fee_breakdown = models.JSONField(default=dict, blank=True)
    tax_breakdown = models.JSONField(default=dict, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    failure_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["provider", "created_at"]),
            models.Index(fields=["payment_type", "created_at"]),
            models.Index(fields=["rail", "created_at"]),
        ]

    def mark_dispatched(self, *, provider_intent_id: str = "", provider_metadata: dict | None = None, commit: bool = True):
        self.status = self.Status.DISPATCHED
        self.dispatched_at = self.dispatched_at or timezone.now()
        if provider_intent_id:
            self.provider_intent_id = str(provider_intent_id)[:128]
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(update_fields=["status", "dispatched_at", "provider_intent_id", "provider_metadata", "updated_at"])
        return self

    def record_provider_reference(
        self,
        *,
        provider_reference: str = "",
        provider_cus: str = "",
        provider_metadata: dict | None = None,
        commit: bool = True,
    ):
        if provider_reference:
            self.provider_reference = str(provider_reference)[:128]
        if provider_cus:
            self.provider_cus = str(provider_cus)[:64]
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(update_fields=["provider_reference", "provider_cus", "provider_metadata", "updated_at"])
        return self

    def mark_processing(self, *, provider_metadata: dict | None = None, commit: bool = True):
        self.status = self.Status.PROCESSING
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(update_fields=["status", "provider_metadata", "updated_at"])
        return self

    def mark_requires_action(self, *, provider_metadata: dict | None = None, commit: bool = True):
        self.status = self.Status.REQUIRES_ACTION
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(update_fields=["status", "provider_metadata", "updated_at"])
        return self

    def mark_succeeded(self, *, provider_intent_id: str = "", provider_metadata: dict | None = None, commit: bool = True):
        self.status = self.Status.SUCCEEDED
        self.completed_at = self.completed_at or timezone.now()
        if provider_intent_id:
            self.provider_intent_id = str(provider_intent_id)[:128]
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "provider_intent_id",
                    "provider_metadata",
                    "updated_at",
                ]
            )
        return self

    def mark_settled(self, *, provider_metadata: dict | None = None, commit: bool = True):
        self.status = self.Status.SETTLED
        self.completed_at = self.completed_at or timezone.now()
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(update_fields=["status", "completed_at", "provider_metadata", "updated_at"])
        return self

    def mark_failed(
        self,
        *,
        failure_code: str = "",
        failure_message: str = "",
        provider_metadata: dict | None = None,
        commit: bool = True,
    ):
        self.status = self.Status.FAILED
        self.completed_at = self.completed_at or timezone.now()
        self.failure_code = str(failure_code or "")[:64]
        self.failure_message = str(failure_message or "")[:2000]
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "failure_code",
                    "failure_message",
                    "provider_metadata",
                    "updated_at",
                ]
            )
        return self

    def mark_cancelled(self, *, failure_message: str = "", provider_metadata: dict | None = None, commit: bool = True):
        self.status = self.Status.CANCELLED
        self.completed_at = self.completed_at or timezone.now()
        self.failure_message = str(failure_message or "")[:2000]
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(update_fields=["status", "completed_at", "failure_message", "provider_metadata", "updated_at"])
        return self


class PayoutBatch(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PROCESSING = "processing", "Processing"
        PARTIAL = "partial", "Partial"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payout_batches",
    )
    provider = models.CharField(max_length=64)
    rail = models.CharField(max_length=24, choices=PaymentIntent.Rail.choices, default=PaymentIntent.Rail.PAYOUT)
    currency = models.CharField(max_length=12, default="COP")
    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATED)
    total_instructions = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    pricing_snapshot = models.JSONField(default=dict, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]


class PayoutInstruction(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        DISPATCHED = "dispatched", "Dispatched"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    batch = models.ForeignKey(PayoutBatch, on_delete=models.CASCADE, related_name="instructions")
    payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payout_instructions",
    )
    beneficiary_name = models.CharField(max_length=160)
    beneficiary_document = models.CharField(max_length=64, blank=True, default="")
    beneficiary_account_ref = models.CharField(max_length=128)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=12, default="COP")
    external_reference = models.CharField(max_length=128, blank=True, default="")
    provider_reference = models.CharField(max_length=128, blank=True, default="")
    provider_cus = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATED)
    fee_breakdown = models.JSONField(default=dict, blank=True)
    tax_breakdown = models.JSONField(default=dict, blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    failure_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["provider_reference"]),
        ]
