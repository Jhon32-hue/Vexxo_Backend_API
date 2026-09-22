from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from common.models import StandardDomainEventOutbox


class OcrRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        REVIEW_REQUIRED = "review_required", "Review required"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ocr_requests",
    )
    document = models.ForeignKey(
        "files.DocumentFile",
        on_delete=models.CASCADE,
        related_name="ocr_requests",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    idempotency_key = models.CharField(max_length=160)
    engine = models.CharField(max_length=64, blank=True, default="")
    client_extracted_text = models.TextField(blank=True, default="")
    client_structured_hint = models.JSONField(default=dict, blank=True)
    extracted_text = models.TextField(blank=True, default="")
    structured_data = models.JSONField(default=dict, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "idempotency_key"],
                name="ocr_request_owner_idempotency_unique",
            )
        ]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["owner", "document"]),
        ]


class OcrFieldObservation(models.Model):
    request = models.ForeignKey(OcrRequest, on_delete=models.CASCADE, related_name="field_observations")
    field_name = models.CharField(max_length=96, db_index=True)
    raw_value = models.TextField(blank=True, default="")
    normalized_value = models.TextField(blank=True, default="")
    confidence_score = models.PositiveSmallIntegerField(null=True, blank=True)
    source = models.CharField(max_length=64)
    extractor_version = models.CharField(max_length=64)
    schema_version = models.CharField(max_length=64, default="documents.ocr.fields.v1")
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="corrections",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ocr_field_corrections",
    )
    correction_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["field_name", "created_at"]
        indexes = [models.Index(fields=["request", "field_name", "created_at"])]


class DocumentDomainEventOutbox(StandardDomainEventOutbox):
    class Meta(StandardDomainEventOutbox.Meta):
        abstract = False
        indexes = [
            models.Index(fields=["status", "occurred_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
            models.Index(fields=["request_id"]),
        ]
