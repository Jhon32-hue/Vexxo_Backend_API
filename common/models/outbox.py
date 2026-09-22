from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


class StandardDomainEventOutbox(models.Model):
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
        abstract = True
        ordering = ["occurred_at"]

    def clean(self):
        super().clean()
        self.aggregate_type = (self.aggregate_type or "").strip()
        self.aggregate_id = (self.aggregate_id or "").strip()
        self.event_type = (self.event_type or "").strip()
        self.idempotency_key = (self.idempotency_key or "").strip()
        required = {
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "idempotency_key": self.idempotency_key,
        }
        errors = {field: f"{field} es requerido." for field, value in required.items() if not value}
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.aggregate_type = (self.aggregate_type or "").strip()
        self.aggregate_id = (self.aggregate_id or "").strip()
        self.event_type = (self.event_type or "").strip()
        self.idempotency_key = (self.idempotency_key or "").strip()
        if self.published_at and self.status != self.Status.PUBLISHED:
            self.status = self.Status.PUBLISHED
        if self.dead_lettered_at and self.status != self.Status.DEAD_LETTER:
            self.status = self.Status.DEAD_LETTER
        super().save(*args, **kwargs)

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
        self.locked_at = None
        self.locked_by = ""
        if self.retry_count >= max(1, int(max_retries or 10)):
            self.status = self.Status.DEAD_LETTER
            self.dead_lettered_at = timezone.now()
            self.dead_letter_reason = self.last_error
            self.next_attempt_at = None
            fields = [
                "status",
                "retry_count",
                "last_error",
                "locked_at",
                "locked_by",
                "dead_lettered_at",
                "dead_letter_reason",
                "next_attempt_at",
            ]
        else:
            self.status = self.Status.FAILED
            delay_seconds = min(300, 2 ** min(self.retry_count, 8))
            self.next_attempt_at = timezone.now() + timezone.timedelta(seconds=delay_seconds)
            fields = [
                "status",
                "retry_count",
                "last_error",
                "locked_at",
                "locked_by",
                "next_attempt_at",
            ]
        if commit:
            self.save(update_fields=fields)

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
                .filter(
                    Q(next_attempt_at__isnull=True)
                    | Q(next_attempt_at__lte=now)
                    | Q(status=self.Status.PROCESSING)
                )
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
