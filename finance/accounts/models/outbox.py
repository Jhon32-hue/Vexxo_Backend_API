"""
Outbox transaccional del dominio de cuentas.

Descripcion general:
- persiste eventos de dominio para publicacion confiable fuera de la transaccion
- soporta reintentos, locking de worker y trazabilidad de errores

Analisis detallado:
- este modelo desacopla la escritura contable local de la publicacion externa
- es clave para no perder eventos de cambios de balance o sincronizacion aunque
  falle un bus, worker o integracion aguas abajo
- `status`, `published_at`, `retry_count` y locking deben mantenerse coherentes;
  por eso el modelo expone helpers de ciclo de vida y normalizacion
- `aggregate_type` deberia seguir una convencion corta, estable y singular,
  por ejemplo `account`; eso facilita particion, filtros y debugging operativo
- `event_type` deberia ser un nombre canonico versionado, por ejemplo
  `finance.account.balance_updated.v1` o la variante estable que el dominio
  adopte; la clave es no mezclar formatos arbitrarios entre productores
- `retry_count` hoy sirve para reintentos simples; si despues Vexxo necesita
  distinguir fallos temporales y permanentes, el modelo ya conserva
  `next_attempt_at`, `last_backoff_seconds` y `dead_lettered_at` para separar
  retries automaticos de eventos agotados operativamente
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class DomainEventOutbox(models.Model):
    """
    Outbox transaccional para publicar eventos de dominio de forma confiable.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"
        DEAD_LETTER = "dead_letter", "Dead letter"

    class PublishResult(models.TextChoices):
        IDLE = "idle", "Idle"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

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
    last_backoff_seconds = models.PositiveIntegerField(default=0)
    dead_lettered_at = models.DateTimeField(null=True, blank=True)
    dead_letter_reason = models.TextField(blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    last_publish_started_at = models.DateTimeField(null=True, blank=True)
    last_publish_finished_at = models.DateTimeField(null=True, blank=True)
    last_publish_duration_ms = models.PositiveIntegerField(default=0)
    last_publish_result = models.CharField(
        max_length=16,
        choices=PublishResult.choices,
        default=PublishResult.IDLE,
    )
    last_publisher = models.CharField(max_length=64, blank=True, default="")

    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["occurred_at"]
        verbose_name = "Domain event outbox"
        verbose_name_plural = "Domain event outbox"
        indexes = [
            models.Index(fields=["status", "occurred_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["published_at", "occurred_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
            models.Index(fields=["correlation_id"]),
            models.Index(fields=["request_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(retry_count__gte=0),
                name="outbox_retry_count_non_negative",
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

        if " " in self.aggregate_type:
            raise ValidationError({"aggregate_type": "aggregate_type no debe contener espacios."})

        if " " in self.event_type:
            raise ValidationError({"event_type": "event_type no debe contener espacios."})

        if self.status == self.Status.PUBLISHED and self.published_at is None:
            raise ValidationError({"published_at": "published_at es requerido cuando status=published."})

        if self.status == self.Status.PROCESSING and not (self.locked_at and self.locked_by):
            raise ValidationError({"status": "status=processing requiere locked_at y locked_by."})

        if self.status == self.Status.DEAD_LETTER and self.dead_lettered_at is None:
            raise ValidationError({"dead_lettered_at": "dead_lettered_at es requerido cuando status=dead_letter."})

        if self.locked_by and self.locked_at is None:
            raise ValidationError({"locked_at": "locked_at es requerido cuando locked_by tiene valor."})

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
            self.last_publish_result = self.PublishResult.SUCCESS
            self.next_attempt_at = None
            self.last_backoff_seconds = 0
            self.dead_letter_reason = ""
        if self.dead_lettered_at and self.status != self.Status.DEAD_LETTER:
            self.status = self.Status.DEAD_LETTER
        if self.status == self.Status.DEAD_LETTER:
            self.published_at = None
        if not self.locked_at:
            self.locked_by = ""
        super().save(*args, **kwargs)

    @property
    def is_published(self) -> bool:
        return self.published_at is not None or self.status == self.Status.PUBLISHED

    @property
    def is_pending(self) -> bool:
        return self.status == self.Status.PENDING and self.published_at is None

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_at and self.locked_by)

    @property
    def is_processing(self) -> bool:
        return self.status == self.Status.PROCESSING and self.is_locked

    def lock(self, worker: str, commit: bool = True):
        self.locked_at = timezone.now()
        self.locked_by = (worker or "")[:64]
        self.status = self.Status.PROCESSING
        if commit:
            self.save(update_fields=["status", "locked_at", "locked_by"])

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
        self.last_backoff_seconds = 0
        self.dead_lettered_at = None
        self.dead_letter_reason = ""
        self.last_error = ""
        self.last_publish_result = self.PublishResult.SUCCESS
        self.release_lock(commit=False)
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "published_at",
                    "next_attempt_at",
                    "last_backoff_seconds",
                    "dead_lettered_at",
                    "dead_letter_reason",
                    "last_error",
                    "last_publish_started_at",
                    "last_publish_finished_at",
                    "last_publish_duration_ms",
                    "last_publish_result",
                    "last_publisher",
                    "locked_at",
                    "locked_by",
                ]
            )

    def mark_dead_letter(self, reason: str, commit: bool = True):
        self.status = self.Status.DEAD_LETTER
        self.next_attempt_at = None
        self.last_backoff_seconds = 0
        self.dead_lettered_at = timezone.now()
        self.dead_letter_reason = (reason or "")[:2000]
        self.last_error = self.dead_letter_reason
        self.last_publish_result = self.PublishResult.FAILED
        self.release_lock(commit=False)
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "next_attempt_at",
                    "last_backoff_seconds",
                    "dead_lettered_at",
                    "dead_letter_reason",
                    "last_error",
                    "last_publish_started_at",
                    "last_publish_finished_at",
                    "last_publish_duration_ms",
                    "last_publish_result",
                    "last_publisher",
                    "locked_at",
                    "locked_by",
                ]
            )

    def mark_failed(
        self,
        error: str,
        *,
        max_retries: int | None = None,
        backoff_seconds: int = 0,
        commit: bool = True,
    ):
        self.status = self.Status.FAILED
        self.retry_count = int(self.retry_count or 0) + 1
        self.last_error = (error or "")[:2000]
        self.last_backoff_seconds = max(0, int(backoff_seconds or 0))
        self.next_attempt_at = timezone.now()
        if self.last_backoff_seconds > 0:
            self.next_attempt_at = self.next_attempt_at + timedelta(seconds=self.last_backoff_seconds)
        self.last_publish_result = self.PublishResult.FAILED
        self.release_lock(commit=False)
        max_retries_value = max(1, int(max_retries or 0)) if max_retries is not None else None
        if max_retries_value is not None and self.retry_count >= max_retries_value:
            self.mark_dead_letter(
                f"{self.last_error} | retries_exhausted={self.retry_count}",
                commit=commit,
            )
            return
        if commit:
            self.save(
                update_fields=[
                    "status",
                    "retry_count",
                    "next_attempt_at",
                    "last_backoff_seconds",
                    "last_error",
                    "last_publish_started_at",
                    "last_publish_finished_at",
                    "last_publish_duration_ms",
                    "last_publish_result",
                    "last_publisher",
                    "locked_at",
                    "locked_by",
                ]
            )
