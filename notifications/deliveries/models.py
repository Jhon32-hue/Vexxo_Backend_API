"""
Persistencia de notificaciones del sistema.

Descripcion general:
- guarda notificaciones internas derivadas de eventos de dominio
- sirve como inbox/feed persistente para UI y futuras entregas por email o push

Analisis detallado:
- `notifications.listeners` decide que evento merece notificarse
- este modelo representa el resultado persistente, no el listener en si
- puede convivir con alertas: una alerta es una pieza de negocio; una
  notificacion es una entrega o item de inbox para el usuario
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationChannel(models.TextChoices):
    IN_APP = "in_app", "In app"
    EMAIL = "email", "Email"
    PUSH = "push", "Push"
    SYSTEM = "system", "System"


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    READ = "read", "Read"


class NotificationCategory(models.TextChoices):
    LIFECYCLE = "lifecycle", "Lifecycle"
    SECURITY = "security", "Security"
    FINANCE = "finance", "Finance"
    COLLABORATION = "collaboration", "Collaboration"
    REMINDER = "reminder", "Reminder"
    INTEGRATION = "integration", "Integration"
    SYSTEM = "system", "System"


class NotificationPriority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class NotificationDelivery(models.Model):
    """
    Notificacion persistente para inbox y futuras entregas multicanal.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
    )
    notification_key = models.CharField(max_length=128, blank=True, default="", db_index=True)
    category = models.CharField(
        max_length=24,
        choices=NotificationCategory.choices,
        default=NotificationCategory.SYSTEM,
        db_index=True,
    )
    priority = models.CharField(
        max_length=16,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
        db_index=True,
    )
    template_key = models.CharField(max_length=128, blank=True, default="")
    template_version = models.PositiveSmallIntegerField(default=1)
    action_path = models.CharField(max_length=255, blank=True, default="")
    channel = models.CharField(max_length=16, choices=NotificationChannel.choices, default=NotificationChannel.IN_APP)
    status = models.CharField(max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.PENDING)
    event_type = models.CharField(max_length=128, blank=True, default="")
    source = models.CharField(max_length=128, blank=True, default="")
    title = models.CharField(max_length=180)
    message = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=190, blank=True, null=True, unique=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "channel"]),
            models.Index(fields=["owner", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["category", "priority", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.channel}:{self.title}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None or self.status == NotificationStatus.READ

    def mark_delivered(self, commit: bool = True):
        self.status = NotificationStatus.DELIVERED
        self.delivered_at = self.delivered_at or timezone.now()
        if commit:
            self.save(update_fields=["status", "delivered_at", "updated_at"])

    def mark_read(self, commit: bool = True):
        self.status = NotificationStatus.READ
        self.read_at = self.read_at or timezone.now()
        if self.delivered_at is None:
            self.delivered_at = self.read_at
        if commit:
            self.save(update_fields=["status", "read_at", "delivered_at", "updated_at"])

    def mark_failed(self, commit: bool = True):
        self.status = NotificationStatus.FAILED
        if commit:
            self.save(update_fields=["status", "updated_at"])
