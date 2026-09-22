import uuid

from django.conf import settings
from django.db import models


class ReportExport(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        DOWNLOADED = "downloaded", "Downloaded"
        EXPIRED = "expired", "Expired"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="report_exports")
    snapshot = models.ForeignKey("snapshots.ReportSnapshot", on_delete=models.PROTECT, related_name="exports")
    export_format = models.CharField(max_length=12, choices=[("json", "JSON"), ("csv", "CSV")], default="json")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    encrypted_content = models.BinaryField(blank=True, default=bytes)
    encryption_envelope = models.JSONField(default=dict, blank=True)
    plaintext_sha256 = models.CharField(max_length=64, blank=True, default="")
    download_token_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    content_purged_at = models.DateTimeField(null=True, blank=True)
    legal_hold = models.BooleanField(default=False)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
