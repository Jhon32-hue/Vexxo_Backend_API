from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def document_upload_path(instance, filename: str) -> str:
    suffix = Path(filename or "document.bin").suffix.lower()[:12]
    return f"documents/{instance.owner_id}/{uuid.uuid4().hex}{suffix}"


class DocumentFile(models.Model):
    class ScanStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEAN = "clean", "Clean"
        INFECTED = "infected", "Infected"
        FAILED = "failed", "Failed"
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        REVIEW_REQUIRED = "review_required", "Review required"
        FAILED = "failed", "Failed"
        DELETED = "deleted", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="document_files",
    )
    file = models.FileField(upload_to=document_upload_path, max_length=500)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)
    is_encrypted = models.BooleanField(default=False)
    encryption_envelope = models.JSONField(default=dict, blank=True)
    scan_status = models.CharField(max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING, db_index=True)
    scan_engine = models.CharField(max_length=64, blank=True, default="")
    scanned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.UPLOADED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    retention_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    legal_hold = models.BooleanField(default=False, db_index=True)
    retention_policy_version = models.CharField(max_length=32, default="documents.retention.v1")
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "sha256"],
                condition=models.Q(deleted_at__isnull=True),
                name="document_owner_active_sha256_unique",
            )
        ]
        indexes = [
            models.Index(fields=["owner", "status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.original_name}"


class DocumentDownloadGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(DocumentFile, on_delete=models.CASCADE, related_name="download_grants")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="document_download_grants")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
