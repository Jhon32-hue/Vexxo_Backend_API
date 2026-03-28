"""
Dispositivos del usuario.

Descripcion general:
- registra dispositivos usados para autenticarse o consumir la app
- sirve para seguridad, trazabilidad, MFA futura y metadata de sesiones

Analisis detallado:
- Vexxo necesita identificar si un login viene de un dispositivo ya conocido,
  confiable o sospechoso
- esta entidad no reemplaza a la sesion; representa el hardware/software
  cliente, mientras `identity.sessions` representa ocurrencias de acceso
- tambien sirve para asociar push tokens, huellas tecnicas y ultimo uso
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class DeviceType(models.TextChoices):
    MOBILE = "mobile", "Mobile"
    WEB = "web", "Web"
    TABLET = "tablet", "Tablet"
    DESKTOP = "desktop", "Desktop"
    SERVER = "server", "Server"
    OTHER = "other", "Other"


class DeviceTrustLevel(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    TRUSTED = "trusted", "Trusted"
    SUSPICIOUS = "suspicious", "Suspicious"
    BLOCKED = "blocked", "Blocked"


class UserDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="identity_devices",
    )
    external_device_id = models.CharField(max_length=128, blank=True, default="")
    fingerprint = models.CharField(max_length=255)
    name = models.CharField(max_length=120, blank=True, default="")
    device_type = models.CharField(max_length=16, choices=DeviceType.choices, default=DeviceType.WEB)
    platform = models.CharField(max_length=32, blank=True, default="")
    os_version = models.CharField(max_length=64, blank=True, default="")
    app_version = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    push_token = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    locale = models.CharField(max_length=16, blank=True, default="")
    timezone_name = models.CharField(max_length=64, blank=True, default="")
    trust_level = models.CharField(max_length=16, choices=DeviceTrustLevel.choices, default=DeviceTrustLevel.UNKNOWN)
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    trusted_at = models.DateTimeField(blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "fingerprint"],
                name="unique_user_device_fingerprint",
            )
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["user", "trust_level"]),
            models.Index(fields=["external_device_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.fingerprint}"

    def touch(self, *, ip_address=None, user_agent=None, commit: bool = True) -> None:
        self.last_seen_at = timezone.now()
        if ip_address:
            self.ip_address = ip_address
        if user_agent:
            self.user_agent = user_agent
        if commit:
            self.save(update_fields=["last_seen_at", "ip_address", "user_agent", "updated_at"])

    def mark_trusted(self, *, commit: bool = True) -> None:
        self.trust_level = DeviceTrustLevel.TRUSTED
        self.trusted_at = timezone.now()
        self.is_active = True
        if commit:
            self.save(update_fields=["trust_level", "trusted_at", "is_active", "updated_at"])

    def mark_suspicious(self, *, commit: bool = True) -> None:
        self.trust_level = DeviceTrustLevel.SUSPICIOUS
        if commit:
            self.save(update_fields=["trust_level", "updated_at"])

    def revoke(self, *, commit: bool = True) -> None:
        self.is_active = False
        self.revoked_at = timezone.now()
        if commit:
            self.save(update_fields=["is_active", "revoked_at", "updated_at"])
