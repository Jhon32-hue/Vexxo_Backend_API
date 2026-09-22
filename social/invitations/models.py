from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class TeamInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        OPENED = "opened", "Opened"
        ACCEPTED = "accepted", "Accepted"
        EXPIRED = "expired", "Expired"
        REVOKED = "revoked", "Revoked"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="invitations")
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="team_invitations",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_team_invitations",
    )
    email = models.EmailField(max_length=254)
    role = models.CharField(max_length=20, choices=[("accountant", "accountant"), ("viewer", "viewer")])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    idempotency_key = models.CharField(max_length=160, blank=True, default="")
    expires_at = models.DateTimeField(db_index=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["team", "status"]),
            models.Index(fields=["email", "status"]),
            models.Index(fields=["invited_user", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "email"],
                condition=Q(status__in=["pending", "opened"]),
                name="uniq_active_team_invitation_email",
            ),
            models.UniqueConstraint(
                fields=["invited_by", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_team_invitation_idempotency",
            ),
        ]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        return super().save(*args, **kwargs)
