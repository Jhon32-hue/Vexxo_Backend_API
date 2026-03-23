from __future__ import annotations

import uuid
from django.db import models
from django.db.models import Q


class DomainEventOutbox(models.Model):
    """
    Outbox transaccional para publicar eventos de dominio de forma confiable.

    Patrón 2:
    - DB update (balance) es inmediato
    - Outbox se guarda en la misma transacción
    - on_commit hace 'ping' realtime liviano
    - worker publica outbox a bus/handlers (Kafka/Redis/HTTP) de forma confiable
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    aggregate_type = models.CharField(max_length=64)
    aggregate_id = models.CharField(max_length=64)

    event_type = models.CharField(max_length=128)

    # clave determinística para evitar duplicados
    idempotency_key = models.CharField(max_length=160, unique=True)

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
            models.Index(fields=["published_at", "occurred_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(retry_count__gte=0),
                name="outbox_retry_count_non_negative",
            )
        ]

    @property
    def is_published(self) -> bool:
        return self.published_at is not None or self.status == self.Status.PUBLISHED