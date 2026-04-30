"""
Challenges temporales de autenticacion y verificacion.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuthChallengePurpose(models.TextChoices):
    PASSWORD_RECOVERY = "password_recovery", "Password recovery"
    EMAIL_VERIFICATION = "email_verification", "Email verification"
    MAGIC_LINK = "magic_link", "Magic link"
    STEP_UP = "step_up", "Step up"


class AuthChallengeChannel(models.TextChoices):
    SMS_CODE = "sms_code", "SMS code"
    EMAIL_LINK = "email_link", "Email link"
    EMAIL_CODE = "email_code", "Email code"


class AuthChallengeStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONSUMED = "consumed", "Consumed"
    BLOCKED = "blocked", "Blocked"
    EXPIRED = "expired", "Expired"
    SUPERSEDED = "superseded", "Superseded"
    FAILED_DISPATCH = "failed_dispatch", "Failed dispatch"


class UserAuthChallenge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="auth_challenges",
    )
    purpose = models.CharField(max_length=32, choices=AuthChallengePurpose.choices)
    channel = models.CharField(max_length=24, choices=AuthChallengeChannel.choices)
    status = models.CharField(
        max_length=24,
        choices=AuthChallengeStatus.choices,
        default=AuthChallengeStatus.PENDING,
    )
    code_hash = models.CharField(max_length=64, blank=True, default="")
    delivery_target_masked = models.CharField(max_length=64, blank=True, default="")
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    requested_ip = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "purpose", "status"], name="users_usera_user_id_b2d082_idx"),
            models.Index(fields=["purpose", "status", "expires_at"], name="users_usera_purpose_9af3c2_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.purpose}:{self.channel}:{self.status}"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    def can_verify(self) -> bool:
        return (
            self.status == AuthChallengeStatus.PENDING
            and not self.is_expired
            and self.failed_attempts < self.max_attempts
        )

    def mark_consumed(self, *, commit: bool = True) -> None:
        self.status = AuthChallengeStatus.CONSUMED
        self.consumed_at = timezone.now()
        if commit:
            self.save(update_fields=["status", "consumed_at", "updated_at"])

    def mark_superseded(self, *, commit: bool = True) -> None:
        self.status = AuthChallengeStatus.SUPERSEDED
        if commit:
            self.save(update_fields=["status", "updated_at"])

    def mark_failed_dispatch(self, *, error: str = "", commit: bool = True) -> None:
        self.status = AuthChallengeStatus.FAILED_DISPATCH
        if error:
            self.metadata = {
                **(self.metadata or {}),
                "dispatch_error": error,
            }
        if commit:
            self.save(update_fields=["status", "metadata", "updated_at"])

    def register_failed_attempt(self, *, commit: bool = True) -> None:
        self.failed_attempts += 1
        if self.failed_attempts >= self.max_attempts:
            self.status = AuthChallengeStatus.BLOCKED
        elif self.is_expired:
            self.status = AuthChallengeStatus.EXPIRED
        if commit:
            self.save(update_fields=["failed_attempts", "status", "updated_at"])

    def mark_expired_if_needed(self, *, commit: bool = True) -> None:
        if self.status == AuthChallengeStatus.PENDING and self.is_expired:
            self.status = AuthChallengeStatus.EXPIRED
            if commit:
                self.save(update_fields=["status", "updated_at"])
