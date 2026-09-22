from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from security.validators import validate_safe_metadata


class IntegrationCredential(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"
        ERROR = "error", "Error"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="integration_credentials",
    )
    provider = models.CharField(max_length=64, db_index=True)
    credential_type = models.CharField(max_length=64)
    external_reference = models.CharField(max_length=160, blank=True, default="")
    encrypted_payload = models.JSONField(default=dict, editable=False)
    key_version = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_rotated_at = models.DateTimeField(null=True, blank=True)
    safe_metadata = models.JSONField(default=dict, blank=True, validators=[validate_safe_metadata])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "credential_type", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "provider", "credential_type", "external_reference"],
                condition=~Q(external_reference=""),
                name="uniq_integration_credential_reference",
            ),
        ]
        indexes = [models.Index(fields=["provider", "status"])]

    def encryption_aad(self) -> str:
        return f"integration-credential:{self.public_id}:{self.owner_id}:{self.provider}:{self.credential_type}"
