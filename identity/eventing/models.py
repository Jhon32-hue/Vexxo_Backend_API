"""
Outbox persistente del bounded context de identidad.

Descripcion general:
- persiste eventos `identity.*` antes de publicarlos al bus
- evita perder eventos de usuarios, sesiones, consentimientos o permisos

Analisis detallado:
- `identity` ya coordina onboarding, seguridad, grants y consentimientos
- si esos eventos se publican solo en memoria, la plataforma queda con menor
  confiabilidad que `accounts`
- este outbox replica el patron correcto: persistir primero, publicar despues
  del commit y dejar rastro para reintentos
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.domain_events import EventPriority


class IdentityDomainEventOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=160, unique=True)
    priority = models.PositiveSmallIntegerField(default=int(EventPriority.NORMAL))
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    causation_id = models.CharField(max_length=64, blank=True, default="")
    payload = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    occurred_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["occurred_at"]
        indexes = [
            models.Index(fields=["status", "occurred_at"]),
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
            models.Index(fields=["correlation_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(retry_count__gte=0),
                name="identity_outbox_retry_count_non_negative",
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
        if int(self.priority or 0) < int(EventPriority.LOW):
            raise ValidationError({"priority": "priority invalido."})
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            raise ValidationError({"published_at": "published_at es requerido cuando status=published."})
        if self.status == self.Status.PROCESSING and not (self.locked_at and self.locked_by):
            raise ValidationError({"status": "status=processing requiere lock."})

    def save(self, *args, **kwargs):
        self.aggregate_type = (self.aggregate_type or "").strip()
        self.aggregate_id = (self.aggregate_id or "").strip()
        self.event_type = (self.event_type or "").strip()
        self.idempotency_key = (self.idempotency_key or "").strip()
        if self.published_at and self.status != self.Status.PUBLISHED:
            self.status = self.Status.PUBLISHED
        if self.locked_at and self.locked_by and self.status == self.Status.PENDING:
            self.status = self.Status.PROCESSING
        if not self.locked_at and self.status == self.Status.PROCESSING:
            self.status = self.Status.PENDING
        if self.status == self.Status.PUBLISHED:
            self.last_error = ""
        if not self.locked_at:
            self.locked_by = ""
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
        self.last_error = ""
        self.release_lock(commit=False)
        if commit:
            self.save(update_fields=["status", "published_at", "last_error", "locked_at", "locked_by"])

    def mark_failed(self, error: str, commit: bool = True):
        self.status = self.Status.FAILED
        self.retry_count = int(self.retry_count or 0) + 1
        self.last_error = (error or "")[:2000]
        self.release_lock(commit=False)
        if commit:
            self.save(update_fields=["status", "retry_count", "last_error", "locked_at", "locked_by"])
