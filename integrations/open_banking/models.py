from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from security.validators import validate_external_payload, validate_safe_metadata


def external_payload_expiry():
    return timezone.now() + timedelta(days=30)


class OpenBankingInstitution(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    code = models.SlugField(max_length=96, unique=True)
    name = models.CharField(max_length=160)
    country = models.CharField(max_length=2, db_index=True)
    logo_path = models.CharField(max_length=255, blank=True, default="")
    logo_sha256 = models.CharField(max_length=64, blank=True, default="")
    logo_license = models.CharField(max_length=120, blank=True, default="")
    logo_provenance = models.CharField(max_length=160, blank=True, default="")
    logo_version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country", "name"]
        indexes = [models.Index(fields=["country", "is_active"])]


class OpenBankingProviderInstitution(models.Model):
    institution = models.ForeignKey(
        OpenBankingInstitution,
        on_delete=models.PROTECT,
        related_name="provider_mappings",
    )
    provider = models.CharField(max_length=64, db_index=True)
    provider_institution_id = models.CharField(max_length=160)
    provider_name = models.CharField(max_length=160, blank=True, default="")
    schema_version = models.CharField(max_length=32, default="open_banking.institution.v1")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "provider_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_institution_id"],
                name="uniq_open_banking_provider_institution",
            ),
        ]


class OpenBankingConnection(models.Model):
    class Status(models.TextChoices):
        PENDING_AUTHORIZATION = "pending_authorization", "Pending authorization"
        CONNECTED = "connected", "Connected"
        SYNCING = "syncing", "Syncing"
        ATTENTION_REQUIRED = "attention_required", "Attention required"
        REVOKED = "revoked", "Revoked"
        ERROR = "error", "Error"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="open_banking_connections",
    )
    consent = models.ForeignKey(
        "consents.UserConsent",
        on_delete=models.PROTECT,
        related_name="open_banking_connections",
    )
    provider = models.CharField(max_length=64, db_index=True)
    idempotency_key = models.CharField(max_length=160, blank=True, default="")
    institution_name = models.CharField(max_length=120, blank=True, default="")
    institution = models.ForeignKey(
        OpenBankingInstitution,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="connections",
    )
    country = models.CharField(max_length=2, blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING_AUTHORIZATION,
        db_index=True,
    )
    external_connection_id = models.CharField(max_length=160, blank=True, default="", db_index=True)
    scopes = models.JSONField(default=list, blank=True)
    safe_metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    last_synced_at = models.DateTimeField(null=True, blank=True)
    next_sync_at = models.DateTimeField(null=True, blank=True)
    credential_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reauthorization_required_at = models.DateTimeField(null=True, blank=True)
    last_provider_event_at = models.DateTimeField(null=True, blank=True)
    last_provider_sequence = models.BigIntegerField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["provider", "external_connection_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_open_banking_owner_idempotency",
            ),
        ]


class OpenBankingAccountLink(models.Model):
    connection = models.ForeignKey(
        OpenBankingConnection,
        on_delete=models.CASCADE,
        related_name="account_links",
    )
    account = models.OneToOneField(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="open_banking_link",
    )
    external_account_id = models.CharField(max_length=160)
    external_mask = models.CharField(max_length=16, blank=True, default="")
    external_type = models.CharField(max_length=64, blank=True, default="")
    sync_cursor = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["connection_id", "account_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "external_account_id"],
                name="uniq_open_banking_external_account",
            ),
        ]


class OpenBankingWebhookReceipt(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"

    provider = models.CharField(max_length=64, db_index=True)
    provider_event_id = models.CharField(max_length=160)
    event_type = models.CharField(max_length=96, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    payload_sha256 = models.CharField(max_length=64)
    signature_verified = models.BooleanField(default=False)
    connection_reference = models.CharField(max_length=160, blank=True, default="", db_index=True)
    provider_occurred_at = models.DateTimeField(null=True, blank=True, db_index=True)
    provider_sequence = models.BigIntegerField(null=True, blank=True)
    safe_metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    error_code = models.CharField(max_length=64, blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_event_id"],
                name="uniq_open_banking_provider_event",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["connection_reference"]),
        ]


class OpenBankingExternalPayload(models.Model):
    class ResourceType(models.TextChoices):
        INSTITUTIONS = "institutions", "Institutions"
        ACCOUNTS = "accounts", "Accounts"
        BALANCES = "balances", "Balances"
        TRANSACTIONS = "transactions", "Transactions"
        WEBHOOK = "webhook", "Webhook"

    class Status(models.TextChoices):
        QUARANTINED = "quarantined", "Quarantined"
        NORMALIZED = "normalized", "Normalized"
        REJECTED = "rejected", "Rejected"
        DEAD = "dead", "Dead letter"
        PURGED = "purged", "Purged"

    connection = models.ForeignKey(
        OpenBankingConnection,
        on_delete=models.CASCADE,
        related_name="external_payloads",
    )
    account_link = models.ForeignKey(
        OpenBankingAccountLink,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="external_payloads",
    )
    provider = models.CharField(max_length=64, db_index=True)
    resource_type = models.CharField(max_length=32, choices=ResourceType.choices, db_index=True)
    payload_sha256 = models.CharField(max_length=64)
    schema_version = models.CharField(max_length=64)
    mapper_version = models.CharField(max_length=64)
    classification = models.CharField(max_length=16, default="restricted")
    provenance = models.CharField(max_length=160)
    cursor_in = models.CharField(max_length=255, blank=True, default="")
    cursor_out = models.CharField(max_length=255, blank=True, default="")
    sanitized_payload = models.JSONField(default=dict, validators=[validate_external_payload])
    safe_metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUARANTINED, db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(default=external_payload_expiry, db_index=True)
    normalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "resource_type", "payload_sha256"],
                name="uniq_open_banking_quarantine_payload",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["provider", "resource_type", "created_at"]),
        ]


class OpenBankingSyncRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        RETRY = "retry", "Retry"
        REAUTHORIZATION = "reauthorization", "Reauthorization"
        DEAD = "dead", "Dead letter"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(OpenBankingConnection, on_delete=models.CASCADE, related_name="sync_runs")
    account_link = models.ForeignKey(OpenBankingAccountLink, on_delete=models.CASCADE, related_name="sync_runs")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    idempotency_key = models.CharField(max_length=180, unique=True)
    cursor_in = models.CharField(max_length=255, blank=True, default="")
    cursor_out = models.CharField(max_length=255, blank=True, default="")
    page_count = models.PositiveIntegerField(default=0)
    item_count = models.PositiveIntegerField(default=0)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    safe_metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]


class OpenBankingTimelineEvent(models.Model):
    connection = models.ForeignKey(OpenBankingConnection, on_delete=models.CASCADE, related_name="timeline_events")
    event_type = models.CharField(max_length=96, db_index=True)
    source = models.CharField(max_length=64)
    status = models.CharField(max_length=32, blank=True, default="")
    provider_event_id = models.CharField(max_length=160, blank=True, default="")
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    safe_metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "pk"]
        indexes = [models.Index(fields=["connection", "occurred_at"])]


class OpenBankingReconciliationIssue(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        IGNORED = "ignored", "Ignored"

    connection = models.ForeignKey(OpenBankingConnection, on_delete=models.CASCADE, related_name="reconciliation_issues")
    account_link = models.ForeignKey(OpenBankingAccountLink, on_delete=models.CASCADE, related_name="reconciliation_issues")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    currency = models.CharField(max_length=3)
    provider_balance = models.DecimalField(max_digits=18, decimal_places=2)
    ledger_balance = models.DecimalField(max_digits=18, decimal_places=2)
    difference = models.DecimalField(max_digits=18, decimal_places=2)
    tolerance = models.DecimalField(max_digits=18, decimal_places=2)
    provider_as_of = models.DateTimeField(null=True, blank=True)
    safe_metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    resolution_notes = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account_link", "status"]),
            models.Index(fields=["connection", "created_at"]),
        ]
