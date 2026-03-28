"""
Sesiones de acceso del usuario.

Descripcion general:
- registra sesiones de autenticacion y acceso de usuario
- permite auditoria, revocacion, correlacion con dispositivos y soporte

Analisis detallado:
- la sesion modela una ocurrencia de login/uso, no el dispositivo permanente
- sirve para guardar IP, user-agent, refresh token JTI, expiracion y revocacion
- se integra con `identity.devices` para saber desde donde ocurrio el acceso
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SessionType(models.TextChoices):
    PASSWORD = "password", "Password"
    SOCIAL = "social", "Social OAuth"
    API = "api", "API"
    INTERNAL = "internal", "Internal"


class SessionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"
    FAILED = "failed", "Failed"


class SessionRiskLevel(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class UserSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="identity_sessions",
    )
    device = models.ForeignKey(
        "devices.UserDevice",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sessions",
    )
    family_id = models.CharField(max_length=128, blank=True, default="")
    session_key = models.CharField(max_length=128, unique=True)
    refresh_jti = models.CharField(max_length=128, blank=True, default="")
    previous_refresh_jti = models.CharField(max_length=128, blank=True, default="")
    access_jti = models.CharField(max_length=128, blank=True, default="")
    session_type = models.CharField(max_length=16, choices=SessionType.choices, default=SessionType.PASSWORD)
    status = models.CharField(max_length=16, choices=SessionStatus.choices, default=SessionStatus.ACTIVE)
    risk_level = models.CharField(max_length=16, choices=SessionRiskLevel.choices, default=SessionRiskLevel.LOW)
    requires_step_up = models.BooleanField(default=False)
    provider = models.CharField(max_length=32, blank=True, default="")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, default="")
    authenticated_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_refreshed_at = models.DateTimeField(blank=True, null=True)
    refresh_rotated_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    revocation_reason = models.CharField(max_length=64, blank=True, default="")
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-authenticated_at", "-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "family_id"]),
            models.Index(fields=["session_key"]),
            models.Index(fields=["refresh_jti"]),
            models.Index(fields=["previous_refresh_jti"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.session_key}:{self.status}"

    def touch(self, *, commit: bool = True) -> None:
        self.last_seen_at = timezone.now()
        if commit:
            self.save(update_fields=["last_seen_at", "updated_at"])

    def revoke(self, *, reason: str = "", commit: bool = True) -> None:
        self.status = SessionStatus.REVOKED
        self.revoked_at = timezone.now()
        self.revocation_reason = reason or self.revocation_reason
        if commit:
            self.save(update_fields=["status", "revoked_at", "revocation_reason", "updated_at"])

    def mark_expired(self, *, commit: bool = True) -> None:
        self.status = SessionStatus.EXPIRED
        if commit:
            self.save(update_fields=["status", "updated_at"])

    def rotate_refresh(self, *, new_refresh_jti: str, new_access_jti: str = "", commit: bool = True) -> None:
        self.previous_refresh_jti = self.refresh_jti
        self.refresh_jti = new_refresh_jti
        self.access_jti = new_access_jti or self.access_jti
        self.last_refreshed_at = timezone.now()
        self.refresh_rotated_at = self.last_refreshed_at
        if commit:
            self.save(
                update_fields=[
                    "previous_refresh_jti",
                    "refresh_jti",
                    "access_jti",
                    "last_refreshed_at",
                    "refresh_rotated_at",
                    "updated_at",
                ]
            )
