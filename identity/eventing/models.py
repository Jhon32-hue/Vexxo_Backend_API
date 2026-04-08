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
from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from common.domain_events import EventPriority


class IdentityDomainEventOutbox(models.Model):
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
    priority = models.PositiveSmallIntegerField(default=int(EventPriority.NORMAL))
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
        if self.status == self.Status.DEAD_LETTER and self.dead_lettered_at is None:
            raise ValidationError({"dead_lettered_at": "dead_lettered_at es requerido cuando status=dead_letter."})

    def save(self, *args, **kwargs):
        self.aggregate_type = (self.aggregate_type or "").strip()
        self.aggregate_id = (self.aggregate_id or "").strip()
        self.event_type = (self.event_type or "").strip()
        self.idempotency_key = (self.idempotency_key or "").strip()
        if self.published_at and self.status != self.Status.PUBLISHED:
            self.status = self.Status.PUBLISHED
        if self.dead_lettered_at and self.status != self.Status.DEAD_LETTER:
            self.status = self.Status.DEAD_LETTER
        if self.locked_at and self.locked_by and self.status == self.Status.PENDING:
            self.status = self.Status.PROCESSING
        if not self.locked_at and self.status == self.Status.PROCESSING:
            self.status = self.Status.PENDING
        if self.status == self.Status.PUBLISHED:
            self.last_error = ""
        if self.status == self.Status.DEAD_LETTER:
            self.next_attempt_at = None
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
        self.next_attempt_at = None
        self.last_error = ""
        self.dead_lettered_at = None
        self.dead_letter_reason = ""
        self.release_lock(commit=False)
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

    def mark_dead_letter(self, reason: str, commit: bool = True):
        self.status = self.Status.DEAD_LETTER
        self.dead_lettered_at = timezone.now()
        self.dead_letter_reason = (reason or "")[:2000]
        self.last_error = self.dead_letter_reason
        self.next_attempt_at = None
        self.release_lock(commit=False)
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "next_attempt_at",
                    "dead_lettered_at",
                    "dead_letter_reason",
                    "last_error",
                    "locked_at",
                    "locked_by",
                ]
            )

    def mark_failed(self, error: str, *, max_retries: int = 10, commit: bool = True):
        self.status = self.Status.FAILED
        self.retry_count = int(self.retry_count or 0) + 1
        self.last_error = (error or "")[:2000]
        self.release_lock(commit=False)
        if self.retry_count >= max(1, int(max_retries or 10)):
            self.mark_dead_letter(
                f"{self.last_error} | retries_exhausted={self.retry_count}",
                commit=commit,
            )
            return
        delay_seconds = min(300, 2 ** min(self.retry_count, 8))
        self.next_attempt_at = timezone.now() + timezone.timedelta(seconds=delay_seconds)
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "retry_count",
                    "next_attempt_at",
                    "last_error",
                    "locked_at",
                    "locked_by",
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


class UserProductUsageProjection(models.Model):
    """
    Read model operativo de uso de producto por usuario.

    Se alimenta desde eventos y productores internos para evitar que mobile y
    el BFF hagan `count()`/`aggregate()` complejos contra OLTP en cada request.
    """

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_usage_projection",
    )
    usage_version = models.PositiveSmallIntegerField(default=1)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    current_day_start = models.DateTimeField(null=True, blank=True)
    current_day_end = models.DateTimeField(null=True, blank=True)

    manual_accounts_count = models.PositiveIntegerField(default=0)
    connected_accounts_count = models.PositiveIntegerField(default=0)
    active_accounts_count = models.PositiveIntegerField(default=0)
    rules_count = models.PositiveIntegerField(default=0)
    ai_used_month = models.PositiveIntegerField(default=0)
    payments_count_month = models.PositiveIntegerField(default=0)
    payments_volume_month = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    payments_count_day = models.PositiveIntegerField(default=0)
    payments_volume_day = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    payouts_count_month = models.PositiveIntegerField(default=0)
    payouts_volume_month = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    payouts_count_day = models.PositiveIntegerField(default=0)
    payouts_volume_day = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    ocr_used_month = models.PositiveIntegerField(default=0)
    scheduled_payments_active_count = models.PositiveIntegerField(default=0)
    shared_memberships_count = models.PositiveIntegerField(default=0)

    last_source = models.CharField(max_length=128, blank=True, default="")
    last_event_type = models.CharField(max_length=128, blank=True, default="")
    last_correlation_id = models.CharField(max_length=64, blank=True, default="")
    refreshed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User product usage projection"
        verbose_name_plural = "User product usage projections"
        indexes = [
            models.Index(fields=["current_period_start", "current_period_end"]),
            models.Index(fields=["last_event_type", "refreshed_at"]),
        ]

    def as_snapshot(self) -> dict:
        return {
            "usage_version": int(self.usage_version or 1),
            "current_period_start": self.current_period_start.isoformat() if self.current_period_start else None,
            "current_period_end": self.current_period_end.isoformat() if self.current_period_end else None,
            "current_day_start": self.current_day_start.isoformat() if self.current_day_start else None,
            "current_day_end": self.current_day_end.isoformat() if self.current_day_end else None,
            "manual_accounts_count": int(self.manual_accounts_count or 0),
            "connected_accounts_count": int(self.connected_accounts_count or 0),
            "active_accounts_count": int(self.active_accounts_count or 0),
            "rules_count": int(self.rules_count or 0),
            "ai_used_month": int(self.ai_used_month or 0),
            "payments_count_month": int(self.payments_count_month or 0),
            "payments_volume_month": str(self.payments_volume_month or 0),
            "payments_count_day": int(self.payments_count_day or 0),
            "payments_volume_day": str(self.payments_volume_day or 0),
            "payouts_count_month": int(self.payouts_count_month or 0),
            "payouts_volume_month": str(self.payouts_volume_month or 0),
            "payouts_count_day": int(self.payouts_count_day or 0),
            "payouts_volume_day": str(self.payouts_volume_day or 0),
            "ocr_used_month": int(self.ocr_used_month or 0),
            "scheduled_payments_active_count": int(self.scheduled_payments_active_count or 0),
            "shared_memberships_count": int(self.shared_memberships_count or 0),
            "last_source": str(self.last_source or ""),
            "last_event_type": str(self.last_event_type or ""),
            "last_correlation_id": str(self.last_correlation_id or ""),
            "refreshed_at": self.refreshed_at.isoformat() if self.refreshed_at else None,
        }


class UserProductUsageProjectionEvent(models.Model):
    """
    Checkpoint persistente de eventos ya aplicados a la proyeccion.

    Permite endurecer idempotencia cuando el proyector usa deltas exactos sobre
    eventos del bus y deja base para una proyeccion 100% incremental.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_usage_projection_events",
    )
    event_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=128, blank=True, default="")
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    fingerprint = models.CharField(max_length=160, blank=True, default="")
    source = models.CharField(max_length=128, blank=True, default="")
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "User product usage projection event"
        verbose_name_plural = "User product usage projection events"
        indexes = [
            models.Index(fields=["owner", "processed_at"]),
            models.Index(fields=["event_type", "processed_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "event_id"],
                name="user_product_usage_projection_event_owner_event_id_uniq",
            )
        ]
