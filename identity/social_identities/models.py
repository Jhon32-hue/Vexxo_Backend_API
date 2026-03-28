"""
Identidades sociales externas vinculadas.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class SocialProvider(models.TextChoices):
    GOOGLE = "google", "Google"
    FACEBOOK = "facebook", "Facebook"


class UserSocialIdentity(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_identities",
    )
    provider = models.CharField(max_length=32, choices=SocialProvider.choices)
    provider_user_id = models.CharField(max_length=128)
    email = models.EmailField(blank=True, default="")
    email_verified = models.BooleanField(default=False)
    full_name = models.CharField(max_length=255, blank=True, default="")
    avatar_url = models.URLField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    linked_at = models.DateTimeField(default=timezone.now)
    last_login_at = models.DateTimeField(blank=True, null=True)
    unlinked_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_user_id"],
                name="unique_social_provider_identity",
            )
        ]
        indexes = [
            models.Index(fields=["user", "provider"]),
            models.Index(fields=["provider", "email"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_user_id}"

    def touch_login(self, commit: bool = True) -> None:
        self.last_login_at = timezone.now()
        if commit:
            self.save(update_fields=["last_login_at", "updated_at"])

    def unlink(self, commit: bool = True) -> None:
        self.is_active = False
        self.unlinked_at = timezone.now()
        if commit:
            self.save(update_fields=["is_active", "unlinked_at", "updated_at"])


class SocialAuthHandoff(models.Model):
    code = models.CharField(max_length=128, unique=True)
    provider = models.CharField(max_length=32, choices=SocialProvider.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_auth_handoffs",
    )
    identity = models.ForeignKey(
        UserSocialIdentity,
        on_delete=models.CASCADE,
        related_name="handoffs",
    )
    login_mode = models.CharField(max_length=32, blank=True, default="")
    created_user = models.BooleanField(default=False)
    linked_identity = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "expires_at"]),
            models.Index(fields=["user", "provider"]),
        ]

    def mark_used(self, *, commit: bool = True) -> None:
        self.used_at = timezone.now()
        if commit:
            self.save(update_fields=["used_at", "updated_at"])

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at >= timezone.now()
