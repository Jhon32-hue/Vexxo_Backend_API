"""
Persistencia ligera de señales realtime.

Descripcion general:
- guarda eventos livianos para UI, polling o futuros WebSocket gateways
- complementa el outbox de dominio sin reemplazarlo
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class RealtimeSignal(models.Model):
    owner_id = models.PositiveBigIntegerField(db_index=True)
    channel = models.CharField(max_length=64, default="accounts")
    event = models.CharField(max_length=128)
    aggregate_type = models.CharField(max_length=64, blank=True, default="")
    aggregate_id = models.CharField(max_length=64, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner_id", "channel", "created_at"]),
            models.Index(fields=["event", "created_at"]),
        ]

    def mark_published(self, commit: bool = True):
        self.published_at = self.published_at or timezone.now()
        if commit:
            self.save(update_fields=["published_at"])
