from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class TransactionIntakeBatch(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", _("recibido")
        PROCESSING = "processing", _("procesando")
        APPLIED = "applied", _("aplicado")
        PARTIAL = "partial", _("parcial")
        FAILED = "failed", _("fallido")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transaction_intake_batches",
    )
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transaction_intake_batches",
    )
    provider = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=64, db_index=True)
    provider_account_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    cursor = models.CharField(max_length=255, blank=True, default="")
    request_id = models.CharField(max_length=64, db_index=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    row_count = models.PositiveIntegerField(default=0)
    raw_summary = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["status", "received_at"]),
            models.Index(fields=["provider", "source", "provider_account_id"]),
            models.Index(fields=["request_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.source}:{self.provider_account_id or 'n/a'} ({self.status})"

    def mark_processing(self, *, commit: bool = True) -> None:
        self.status = self.Status.PROCESSING
        self.last_error = ""
        if commit:
            self.save(update_fields=["status", "last_error", "updated_at"])

    def mark_applied(self, *, partial: bool = False, commit: bool = True) -> None:
        self.status = self.Status.PARTIAL if partial else self.Status.APPLIED
        self.applied_at = timezone.now()
        self.last_error = ""
        if commit:
            self.save(update_fields=["status", "applied_at", "last_error", "updated_at"])

    def mark_failed(self, error: str, *, commit: bool = True) -> None:
        self.status = self.Status.FAILED
        self.last_error = (error or "")[:2000]
        if commit:
            self.save(update_fields=["status", "last_error", "updated_at"])


class TransactionReconciliationIssue(models.Model):
    class IssueType(models.TextChoices):
        CORRECTION_REQUIRED = "correction_required", _("correccion requerida")
        REVERSE_REQUIRED = "reverse_required", _("reverso requerido")
        MATERIAL_MISMATCH = "material_mismatch", _("mismatch material")

    class Status(models.TextChoices):
        OPEN = "open", _("abierto")
        RESOLVED = "resolved", _("resuelto")
        IGNORED = "ignored", _("ignorado")

    class ResolutionAction(models.TextChoices):
        APPLY_PROVIDER_UPDATE = "apply_provider_update", _("aplicar actualizacion del proveedor")
        CREATE_ADJUSTMENT = "create_adjustment", _("crear ajuste compensatorio")
        CREATE_REVERSAL = "create_reversal", _("crear reverso compensatorio")
        IGNORE = "ignore", _("ignorar")

    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.CASCADE,
        related_name="reconciliation_issues",
    )
    source_link = models.ForeignKey(
        "transactions.TransactionSourceLink",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="issues",
    )
    issue_type = models.CharField(max_length=32, choices=IssueType.choices, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    resolution_action = models.CharField(max_length=32, choices=ResolutionAction.choices, blank=True, default="")
    resolution_notes = models.TextField(blank=True, default="")
    resolution_payload = models.JSONField(default=dict, blank=True)
    resolved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_transaction_reconciliation_issues",
    )
    resolution_transaction = models.ForeignKey(
        "transactions.Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolution_source_issues",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["issue_type", "status"]),
            models.Index(fields=["transaction", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.issue_type} tx={self.transaction_id} ({self.status})"

    def mark_resolved(
        self,
        *,
        action: str,
        actor=None,
        notes: str = "",
        payload: dict | None = None,
        resolution_transaction=None,
        commit: bool = True,
    ) -> None:
        self.status = self.Status.RESOLVED
        self.resolution_action = action
        self.resolution_notes = notes or ""
        self.resolution_payload = payload or {}
        self.resolved_by = actor if getattr(actor, "pk", None) else None
        self.resolution_transaction = resolution_transaction
        self.resolved_at = timezone.now()
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "resolution_action",
                    "resolution_notes",
                    "resolution_payload",
                    "resolved_by",
                    "resolution_transaction",
                    "resolved_at",
                    "updated_at",
                ]
            )

    def mark_ignored(self, *, actor=None, notes: str = "", payload: dict | None = None, commit: bool = True) -> None:
        self.status = self.Status.IGNORED
        self.resolution_action = self.ResolutionAction.IGNORE
        self.resolution_notes = notes or ""
        self.resolution_payload = payload or {}
        self.resolved_by = actor if getattr(actor, "pk", None) else None
        self.resolution_transaction = None
        self.resolved_at = timezone.now()
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "resolution_action",
                    "resolution_notes",
                    "resolution_payload",
                    "resolved_by",
                    "resolution_transaction",
                    "resolved_at",
                    "updated_at",
                ]
            )


class TransactionIntakeReceipt(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", _("recibido")
        PROCESSING = "processing", _("procesando")
        MATERIALIZED = "materialized", _("materializado")
        UPDATED = "updated", _("actualizado")
        DUPLICATE = "duplicate", _("duplicado")
        NOOP = "noop", _("sin cambios")
        CORRECTED = "corrected", _("correccion detectada")
        REVERSED = "reversed", _("reverso detectado")
        FAILED = "failed", _("fallido")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        TransactionIntakeBatch,
        on_delete=models.CASCADE,
        related_name="receipts",
    )
    provider = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=64, db_index=True)
    provider_account_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    external_id = models.CharField(max_length=128, blank=True, default="")
    provider_event_id = models.CharField(max_length=128, blank=True, default="")
    canonical_fingerprint = models.CharField(max_length=128, blank=True, default="", db_index=True)
    normalized_payload = models.JSONField(default=dict)
    raw_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    duplicate_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicates",
    )
    materialized_transaction = models.ForeignKey(
        "transactions.Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="intake_receipts",
    )
    reconciliation_issue = models.ForeignKey(
        TransactionReconciliationIssue,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="receipts",
    )
    seen_count = models.PositiveIntegerField(default=1)
    last_error = models.TextField(blank=True, default="")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["first_seen_at"]
        indexes = [
            models.Index(fields=["status", "first_seen_at"]),
            models.Index(fields=["provider", "source", "provider_account_id", "external_id"]),
            models.Index(fields=["provider", "source", "provider_account_id", "canonical_fingerprint"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.external_id or self.canonical_fingerprint} ({self.status})"

    def touch_duplicate(self, *, duplicate_of=None, status: str | None = None, commit: bool = True) -> None:
        self.seen_count = int(self.seen_count or 0) + 1
        self.last_seen_at = timezone.now()
        self.duplicate_of = duplicate_of
        self.status = status or self.Status.DUPLICATE
        if commit:
            self.save(update_fields=["seen_count", "last_seen_at", "duplicate_of", "status", "updated_at"])


class TransactionExternalDetails(models.Model):
    class CreditDebitIndicator(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        DEBIT = "debit", _("debito")
        CREDIT = "credit", _("credito")

    class Rail(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        MANUAL = "manual", _("manual")
        OPEN_BANKING = "open_banking", _("open banking")
        BANK_TRANSFER = "bank_transfer", _("transferencia bancaria")
        CARD = "card", _("tarjeta")
        WALLET = "wallet", _("wallet")
        PAYMENT_NETWORK = "payment_network", _("red de pagos")
        MESSAGE = "message", _("mensaje")
        IMPORT = "import", _("importacion")
        OTHER = "other", _("otro")

    class Channel(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        MANUAL = "manual", _("manual")
        CARD_PRESENT = "card_present", _("tarjeta presente")
        ECOMMERCE = "ecommerce", _("ecommerce")
        BANK_TRANSFER = "bank_transfer", _("transferencia bancaria")
        WALLET = "wallet", _("wallet")
        SMS = "sms", _("sms")
        EMAIL = "email", _("email")
        MESSAGE_INFERRED = "message_inferred", _("mensaje inferido")
        API = "api", _("api")
        IMPORT = "import", _("importacion")
        OTHER = "other", _("otro")

    class AuthorizationStatus(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        PENDING = "pending", _("pendiente")
        AUTHORIZED = "authorized", _("autorizada")
        DECLINED = "declined", _("rechazada")
        CANCELED = "canceled", _("cancelada")
        FAILED = "failed", _("fallida")
        REVERSED = "reversed", _("revertida")

    class SettlementStatus(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        PENDING = "pending", _("pendiente")
        SETTLED = "settled", _("liquidada")
        PARTIAL = "partial", _("parcial")
        FAILED = "failed", _("fallida")
        CANCELED = "canceled", _("cancelada")
        REVERSED = "reversed", _("revertida")

    class DataOrigin(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        MANUAL = "manual", _("manual")
        OPEN_BANKING = "open_banking", _("open banking")
        PAYMENT_NETWORK = "payment_network", _("red de pagos")
        WALLET = "wallet", _("wallet")
        MESSAGE = "message", _("mensaje")
        IMPORT = "import", _("importacion")
        INFERRED = "inferred", _("inferida")
        PAYMENT_INTENT = "payment_intent", _("payment intent")

    class InferenceStatus(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        INFERRED = "inferred", _("inferida")
        NEEDS_CONFIRMATION = "needs_confirmation", _("requiere confirmacion")
        USER_CONFIRMED = "user_confirmed", _("confirmada por usuario")
        PROVIDER_CONFIRMED = "provider_confirmed", _("confirmada por proveedor")
        REJECTED = "rejected", _("rechazada")

    transaction = models.OneToOneField(
        "transactions.Transaction",
        on_delete=models.CASCADE,
        related_name="external_details",
    )
    description = models.CharField(max_length=255, blank=True, default="")
    transaction_information = models.JSONField(default=dict, blank=True)
    booking_datetime = models.DateTimeField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    credit_debit_indicator = models.CharField(
        max_length=16,
        choices=CreditDebitIndicator.choices,
        default=CreditDebitIndicator.UNSPECIFIED,
        blank=True,
    )
    merchant_name = models.CharField(max_length=160, blank=True, default="")
    merchant_category_code = models.CharField(max_length=16, blank=True, default="")
    counterparty_name = models.CharField(max_length=160, blank=True, default="")
    counterparty_account_ref = models.CharField(max_length=128, blank=True, default="")
    rail = models.CharField(max_length=32, choices=Rail.choices, default=Rail.UNSPECIFIED, blank=True)
    rail_reference = models.CharField(max_length=128, blank=True, default="")
    authorization_status = models.CharField(
        max_length=16,
        choices=AuthorizationStatus.choices,
        default=AuthorizationStatus.UNSPECIFIED,
        blank=True,
    )
    settlement_status = models.CharField(
        max_length=16,
        choices=SettlementStatus.choices,
        default=SettlementStatus.UNSPECIFIED,
        blank=True,
    )
    authorized_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    balance_after_transaction = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    original_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField(max_length=3, blank=True, default="")
    fx_rate = models.DecimalField(max_digits=16, decimal_places=8, null=True, blank=True)
    country_code = models.CharField(max_length=2, blank=True, default="")
    channel = models.CharField(max_length=32, choices=Channel.choices, default=Channel.UNSPECIFIED, blank=True)
    confidence_score = models.PositiveSmallIntegerField(null=True, blank=True)
    data_origin = models.CharField(
        max_length=32,
        choices=DataOrigin.choices,
        default=DataOrigin.UNSPECIFIED,
        blank=True,
    )
    message_id = models.CharField(max_length=128, blank=True, default="")
    sender_id = models.CharField(max_length=128, blank=True, default="")
    received_at = models.DateTimeField(null=True, blank=True)
    parsed_text = models.TextField(blank=True, default="")
    parser_version = models.CharField(max_length=64, blank=True, default="")
    needs_user_confirmation = models.BooleanField(default=False)
    inference_status = models.CharField(
        max_length=32,
        choices=InferenceStatus.choices,
        default=InferenceStatus.UNSPECIFIED,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["rail", "channel"]),
            models.Index(fields=["data_origin", "confidence_score"]),
            models.Index(fields=["merchant_name"]),
            models.Index(fields=["counterparty_name"]),
        ]

    def __str__(self) -> str:
        return f"external_details tx={self.transaction_id} rail={self.rail or 'n/a'}"


class TransactionSourceLink(models.Model):
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.CASCADE,
        related_name="source_links",
    )
    provider = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=64, db_index=True)
    provider_account_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    external_id = models.CharField(max_length=128, blank=True, default="")
    canonical_fingerprint = models.CharField(max_length=128, blank=True, default="")
    provider_status = models.CharField(max_length=64, blank=True, default="")
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_normalized_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["provider", "source", "provider_account_id"]),
            models.Index(fields=["transaction", "provider"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "source", "provider_account_id", "external_id"],
                condition=~Q(external_id=""),
                name="unique_transaction_source_link_external_id",
            ),
            models.UniqueConstraint(
                fields=["provider", "source", "provider_account_id", "canonical_fingerprint"],
                condition=~Q(canonical_fingerprint=""),
                name="unique_transaction_source_link_fingerprint",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.external_id or self.canonical_fingerprint} -> tx={self.transaction_id}"
