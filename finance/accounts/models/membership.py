from __future__ import annotations

import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from finance.accounts.domain.enums import AccountAccessMode, AccountMembershipRole

User = get_user_model()


class AccountMembership(models.Model):
    """
    Membresía de una cuenta (modo social).

    Fuente de verdad para permisos de:
    - ver
    - postear transacciones
    - administrar miembros
    - administrar settings
    - ver analytics

    Mantiene compatibilidad con Account.read_only/shared_from_user (legacy),
    pero la regla moderna se lee desde aquí.
    """

    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_memberships")

    role = models.CharField(
        max_length=16,
        choices=AccountMembershipRole.choices,
        default=AccountMembershipRole.MEMBER,
    )
    access_mode = models.CharField(
        max_length=16,
        choices=AccountAccessMode.choices,
        default=AccountAccessMode.FULL,
    )

    # Permisos explícitos (más flexible que solo role)
    can_post_transactions = models.BooleanField(default=True)
    can_manage_members = models.BooleanField(default=False)
    can_manage_account_settings = models.BooleanField(default=False)
    can_view_analytics = models.BooleanField(default=True)

    # Invitación / lifecycle
    invited_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invited_account_memberships",
    )
    invitation_token = models.UUIDField(default=uuid.uuid4, editable=False)
    invitation_sent_at = models.DateTimeField(null=True, blank=True)

    joined_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    # metadata opcional para futuras extensiones (teams, tags, etc.)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Account membership"
        verbose_name_plural = "Account memberships"
        constraints = [
            models.UniqueConstraint(fields=["account", "user"], name="unique_account_membership_per_user"),
            # Solo 1 OWNER activo por cuenta (si tu negocio lo quiere así)
            models.UniqueConstraint(
                fields=["account"],
                condition=Q(role=AccountMembershipRole.OWNER) & Q(is_active=True),
                name="unique_active_owner_per_account",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["account", "is_active"]),
            models.Index(fields=["account", "role"]),
            models.Index(fields=["account", "access_mode"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.account_id}:{self.role}"

    @property
    def is_read_only(self) -> bool:
        return self.access_mode == AccountAccessMode.READ_ONLY

    def clean(self) -> None:
        # coherencia de estados
        if not self.is_active and self.revoked_at is None:
            # no forzamos, pero sugerimos consistencia
            pass

        # si es read_only, no debería poder postear
        if self.access_mode == AccountAccessMode.READ_ONLY and self.can_post_transactions:
            raise ValidationError({"can_post_transactions": _("Read-only no puede postear transacciones.")})

        # owner/admin deberían poder ver analytics
        if self.role in {AccountMembershipRole.OWNER, AccountMembershipRole.ADMIN} and not self.can_view_analytics:
            raise ValidationError({"can_view_analytics": _("Owner/Admin deben poder ver analytics.")})

    def activate(self, *, joined_at=None, commit: bool = True):
        from django.utils import timezone
        self.is_active = True
        self.revoked_at = None
        self.joined_at = joined_at or timezone.now()
        if commit:
            self.save(update_fields=["is_active", "revoked_at", "joined_at"])

    def revoke(self, *, revoked_at=None, commit: bool = True):
        from django.utils import timezone
        self.is_active = False
        self.revoked_at = revoked_at or timezone.now()
        if commit:
            self.save(update_fields=["is_active", "revoked_at"])
