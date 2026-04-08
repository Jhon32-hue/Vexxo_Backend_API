"""
Modelo canonico para intents de pago embebido.

No representa el ledger final. Representa la intencion operativa de enviar un
comando a un PSP/retailer externo y recibir callbacks posteriores.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
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
        REVERSED = "reversed", "Reversed"
        DISPUTED = "disputed", "Disputed"

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

    def mark_reversed(
        self,
        *,
        failure_message: str = "",
        provider_metadata: dict | None = None,
        commit: bool = True,
    ):
        self.status = self.Status.REVERSED
        self.completed_at = self.completed_at or timezone.now()
        self.failure_message = str(failure_message or "")[:2000]
        if provider_metadata:
            merged = dict(self.provider_metadata or {})
            merged.update(provider_metadata or {})
            self.provider_metadata = merged
        if commit:
            self.save(update_fields=["status", "completed_at", "failure_message", "provider_metadata", "updated_at"])
        return self

    def mark_disputed(
        self,
        *,
        failure_message: str = "",
        provider_metadata: dict | None = None,
        commit: bool = True,
    ):
        self.status = self.Status.DISPUTED
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


class PaymentDomainEventOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"
        DEAD_LETTER = "dead_letter", "Dead letter"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=160, unique=True)
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    causation_id = models.CharField(max_length=64, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    payload = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    occurred_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True, default="")
    dead_lettered_at = models.DateTimeField(null=True, blank=True)
    dead_letter_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["occurred_at"]
        indexes = [
            models.Index(fields=["status", "occurred_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
            models.Index(fields=["correlation_id"]),
            models.Index(fields=["request_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(retry_count__gte=0),
                name="payment_outbox_retry_count_non_negative",
            )
        ]

    def clean(self):
        super().clean()
        self.aggregate_type = (self.aggregate_type or "").strip()
        self.aggregate_id = (self.aggregate_id or "").strip()
        self.event_type = (self.event_type or "").strip()
        self.idempotency_key = (self.idempotency_key or "").strip()
        if not self.aggregate_type:
            raise ValidationError({"aggregate_type": "aggregate_type es requerido."})
        if not self.aggregate_id:
            raise ValidationError({"aggregate_id": "aggregate_id es requerido."})
        if not self.event_type:
            raise ValidationError({"event_type": "event_type es requerido."})

    def save(self, *args, **kwargs):
        self.aggregate_type = (self.aggregate_type or "").strip()
        self.aggregate_id = (self.aggregate_id or "").strip()
        self.event_type = (self.event_type or "").strip()
        self.idempotency_key = (self.idempotency_key or "").strip()
        if self.published_at and self.status != self.Status.PUBLISHED:
            self.status = self.Status.PUBLISHED
        if self.dead_lettered_at and self.status != self.Status.DEAD_LETTER:
            self.status = self.Status.DEAD_LETTER
        if self.locked_at and self.locked_by and self.status in {self.Status.PENDING, self.Status.FAILED}:
            self.status = self.Status.PROCESSING
        if not self.locked_at and self.status == self.Status.PROCESSING:
            self.status = self.Status.PENDING
        super().save(*args, **kwargs)

    def release_lock(self, commit: bool = True):
        self.locked_at = None
        self.locked_by = ""
        if self.status == self.Status.PROCESSING:
            self.status = self.Status.PENDING
        if commit:
            self.save(update_fields=["status", "locked_at", "locked_by"])

    def mark_published(self, commit: bool = True):
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.next_attempt_at = None
        self.last_error = ""
        self.dead_lettered_at = None
        self.dead_letter_reason = ""
        self.locked_at = None
        self.locked_by = ""
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "published_at",
                    "next_attempt_at",
                    "last_error",
                    "dead_lettered_at",
                    "dead_letter_reason",
                    "locked_at",
                    "locked_by",
                ]
            )

    def mark_failed(self, error: str, *, max_retries: int = 10, commit: bool = True):
        self.retry_count = int(self.retry_count or 0) + 1
        self.last_error = (error or "")[:2000]
        self.release_lock(commit=False)
        if self.retry_count >= max(1, int(max_retries or 10)):
            self.status = self.Status.DEAD_LETTER
            self.dead_lettered_at = timezone.now()
            self.dead_letter_reason = self.last_error
            self.next_attempt_at = None
            if commit:
                self.save(
                    update_fields=[
                        "status",
                        "retry_count",
                        "last_error",
                        "locked_at",
                        "locked_by",
                        "dead_lettered_at",
                        "dead_letter_reason",
                        "next_attempt_at",
                    ]
                )
            return
        self.status = self.Status.FAILED
        delay_seconds = min(300, 2 ** min(self.retry_count, 8))
        self.next_attempt_at = timezone.now() + timezone.timedelta(seconds=delay_seconds)
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "retry_count",
                    "last_error",
                    "locked_at",
                    "locked_by",
                    "next_attempt_at",
                ]
            )

    def claim_for_processing(self, *, worker_id: str) -> bool:
        if self.published_at:
            return False
        now = timezone.now()
        stale_threshold = now - timezone.timedelta(minutes=15)
        with transaction.atomic():
            updated = (
                self.__class__.objects.filter(pk=self.pk, published_at__isnull=True)
                .filter(
                    Q(status__in=[self.Status.PENDING, self.Status.FAILED])
                    | Q(status=self.Status.PROCESSING, locked_at__lte=stale_threshold)
                )
                .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now) | Q(status=self.Status.PROCESSING))
                .update(
                    status=self.Status.PROCESSING,
                    locked_at=now,
                    locked_by=(worker_id or "")[:64],
                )
            )
        if updated:
            self.status = self.Status.PROCESSING
            self.locked_at = now
            self.locked_by = (worker_id or "")[:64]
            return True
        return False


class PaymentProviderCallbackReceipt(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    provider = models.CharField(max_length=64)
    callback_type = models.CharField(max_length=64, blank=True, default="status")
    external_reference = models.CharField(max_length=128, blank=True, default="")
    provider_intent_id = models.CharField(max_length=128, blank=True, default="")
    provider_reference = models.CharField(max_length=128, blank=True, default="")
    payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="callback_receipts",
    )
    signature_valid = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    raw_payload = models.JSONField(default=dict, blank=True)
    normalized_payload = models.JSONField(default=dict, blank=True)
    raw_headers = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["provider_reference"]),
            models.Index(fields=["external_reference"]),
            models.Index(fields=["provider_intent_id"]),
        ]


class PaymentSettlementRecord(models.Model):
    class Status(models.TextChoices):
        RECORDED = "recorded", "Recorded"
        RECONCILED = "reconciled", "Reconciled"
        MISMATCH = "mismatch", "Mismatch"

    payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="settlement_records",
    )
    provider = models.CharField(max_length=64)
    rail = models.CharField(max_length=24, blank=True, default="")
    settlement_reference = models.CharField(max_length=128, blank=True, default="")
    provider_reference = models.CharField(max_length=128, blank=True, default="")
    provider_cus = models.CharField(max_length=64, blank=True, default="")
    amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    fee_snapshot = models.JSONField(default=dict, blank=True)
    settlement_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECORDED)
    settled_at = models.DateTimeField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["provider", "recorded_at"]),
            models.Index(fields=["status", "recorded_at"]),
            models.Index(fields=["settlement_reference"]),
            models.Index(fields=["provider_reference"]),
        ]


class PaymentOperationalCase(models.Model):
    class Kind(models.TextChoices):
        ERROR = "error", "Error"
        REVERSAL = "reversal", "Reversal"
        DISPUTE = "dispute", "Dispute"
        REFUND = "refund", "Refund"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operational_cases",
    )
    provider = models.CharField(max_length=64)
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.ERROR)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    provider_reference = models.CharField(max_length=128, blank=True, default="")
    provider_case_reference = models.CharField(max_length=128, blank=True, default="")
    amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    currency = models.CharField(max_length=12, default="COP")
    details = models.JSONField(default=dict, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        indexes = [
            models.Index(fields=["provider", "kind", "opened_at"]),
            models.Index(fields=["status", "opened_at"]),
            models.Index(fields=["provider_reference"]),
            models.Index(fields=["provider_case_reference"]),
        ]
