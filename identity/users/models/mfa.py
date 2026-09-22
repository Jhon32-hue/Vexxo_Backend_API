from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from security.validators import validate_safe_metadata


class UserMfaMethod(models.Model):
    class Method(models.TextChoices):
        TOTP = "totp", "Authenticator app"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_methods")
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.TOTP)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    secret_credential = models.OneToOneField(
        "integration_credentials.IntegrationCredential",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mfa_method",
    )
    recovery_code_hashes = models.JSONField(default=list, blank=True, validators=[validate_safe_metadata])
    last_totp_counter = models.BigIntegerField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "method"],
                condition=models.Q(status__in=["pending", "active"]),
                name="uniq_active_user_mfa_method",
            ),
        ]
