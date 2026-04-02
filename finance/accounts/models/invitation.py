"""
Invitaciones versionadas de colaboracion sobre cuentas.

Descripcion general:
- separa el ciclo de vida de una invitacion del estado estable de
  `AccountMembership`
- permite expiracion, reenvio, apertura, aceptacion y revocacion con trazas
  propias

Analisis detallado:
- cada fila representa un intento de invitacion
- `AccountMembership` sigue siendo la fuente canonica de permisos efectivos,
  pero la historia social de invitaciones vive aqui
- `is_current` marca la invitacion vigente para la membresia
"""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

User = get_user_model()


class AccountInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        OPENED = "opened", "Opened"
        ACCEPTED = "accepted", "Accepted"
        EXPIRED = "expired", "Expired"
        REVOKED = "revoked", "Revoked"

    membership = models.ForeignKey(
        "accounts.AccountMembership",
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="membership_invitations",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="account_invitations",
    )
    invited_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_account_invitations",
    )
    resend_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reissues",
    )

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempt_number = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True, db_index=True)
    channel = models.CharField(max_length=32, blank=True, default="direct_link")

    sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account invitation"
        verbose_name_plural = "Account invitations"
        indexes = [
            models.Index(fields=["membership", "is_current"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["account", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["membership"],
                condition=Q(is_current=True),
                name="uniq_curr_inv_per_membership",
            ),
        ]

    def __str__(self) -> str:
        return f"Invitation(membership={self.membership_id}, status={self.status}, attempt={self.attempt_number})"

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_pending(self) -> bool:
        return self.status in {self.Status.PENDING, self.Status.OPENED} and not self.is_expired

    def clean(self):
        super().clean()
        if self.membership_id:
            if self.account_id and self.account_id != self.membership.account_id:
                raise ValidationError({"account": "account debe coincidir con membership.account."})
            if self.user_id and self.user_id != self.membership.user_id:
                raise ValidationError({"user": "user debe coincidir con membership.user."})
            self.account_id = self.membership.account_id
            self.user_id = self.membership.user_id
            if not self.invited_by_id:
                self.invited_by_id = self.membership.invited_by_id

        if self.accepted_at and self.sent_at and self.accepted_at < self.sent_at:
            raise ValidationError({"accepted_at": "accepted_at no puede ser anterior a sent_at."})
        if self.opened_at and self.sent_at and self.opened_at < self.sent_at:
            raise ValidationError({"opened_at": "opened_at no puede ser anterior a sent_at."})
        if self.revoked_at and self.sent_at and self.revoked_at < self.sent_at:
            raise ValidationError({"revoked_at": "revoked_at no puede ser anterior a sent_at."})

    def save(self, *args, **kwargs):
        if self.membership_id:
            self.account_id = self.membership.account_id
            self.user_id = self.membership.user_id
            if not self.invited_by_id:
                self.invited_by_id = self.membership.invited_by_id
        super().save(*args, **kwargs)

    def mark_opened(self, *, opened_at=None, commit: bool = True):
        if self.is_expired and self.status not in {self.Status.ACCEPTED, self.Status.REVOKED, self.Status.EXPIRED}:
            self.expire(commit=False)
        if self.status == self.Status.PENDING:
            self.status = self.Status.OPENED
        self.opened_at = opened_at or timezone.now()
        if commit:
            self.save(update_fields=["status", "opened_at", "updated_at"])

    def accept(self, *, accepted_at=None, commit: bool = True):
        accepted_value = accepted_at or timezone.now()
        self.status = self.Status.ACCEPTED
        self.accepted_at = accepted_value
        if self.opened_at is None:
            self.opened_at = accepted_value
        self.is_current = False
        if commit:
            self.save(update_fields=["status", "accepted_at", "opened_at", "is_current", "updated_at"])

    def revoke(self, *, revoked_at=None, commit: bool = True):
        self.status = self.Status.REVOKED
        self.revoked_at = revoked_at or timezone.now()
        self.is_current = False
        if commit:
            self.save(update_fields=["status", "revoked_at", "is_current", "updated_at"])

    def expire(self, *, expired_at=None, commit: bool = True):
        self.status = self.Status.EXPIRED
        self.revoked_at = expired_at or timezone.now()
        self.is_current = False
        if commit:
            self.save(update_fields=["status", "revoked_at", "is_current", "updated_at"])
