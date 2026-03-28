"""
Permisos y grants de producto del usuario.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class PermissionStatus(models.TextChoices):
    GRANTED = "granted", "Granted"
    DENIED = "denied", "Denied"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


class PermissionSource(models.TextChoices):
    SYSTEM = "system", "System"
    PLAN = "plan", "Plan"
    ADMIN = "admin", "Admin"
    CONSENT = "consent", "Consent"
    SUPPORT = "support", "Support"


class PermissionGrantKind(models.TextChoices):
    MANUAL = "manual", "Manual"
    ENTITLEMENT = "entitlement", "Entitlement"
    OVERRIDE = "override", "Override"


class UserPermissionGrant(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="identity_permission_grants",
    )
    permission_code = models.CharField(max_length=128)
    scope_type = models.CharField(max_length=64, blank=True, default="global")
    scope_id = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=16, choices=PermissionStatus.choices, default=PermissionStatus.GRANTED)
    source = models.CharField(max_length=16, choices=PermissionSource.choices, default=PermissionSource.SYSTEM)
    grant_kind = models.CharField(max_length=16, choices=PermissionGrantKind.choices, default=PermissionGrantKind.MANUAL)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="granted_identity_permissions",
    )
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["permission_code", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "permission_code", "scope_type", "scope_id", "source", "grant_kind"],
                name="unique_identity_permission_scope_source_kind",
            )
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["permission_code", "status"]),
            models.Index(fields=["user", "grant_kind", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.permission_code}:{self.status}"

    def revoke(self, *, commit: bool = True) -> None:
        self.status = PermissionStatus.REVOKED
        self.revoked_at = timezone.now()
        if commit:
            self.save(update_fields=["status", "revoked_at", "updated_at"])

    def deny(self, *, commit: bool = True) -> None:
        self.status = PermissionStatus.DENIED
        self.revoked_at = None
        if commit:
            self.save(update_fields=["status", "revoked_at", "updated_at"])
