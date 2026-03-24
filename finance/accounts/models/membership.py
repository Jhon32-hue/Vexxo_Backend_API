"""
Membresias sociales de cuentas.

Descripcion general:
- define quien puede ver u operar una cuenta compartida
- combina rol, modo de acceso y permisos explicitos

Analisis detallado:
- este modelo es la fuente moderna de permisos compartidos en Vexxo
- complementa banderas legacy en `Account` como `read_only` o `shared_from_user`
- soporta escenarios reales de finanzas personales: pareja, familia, roomies,
  equipos o cuentas observadas
- debe considerarse el sistema canonico de permisos compartidos; cualquier capa
  legacy paralela deberia tratarse como compatibilidad temporal
- para mantener coherencia, normaliza permisos incompatibles segun `role`,
  `access_mode` y la relacion con el owner real de la cuenta
- `AccountAccess` todavia puede coexistir por compatibilidad, pero no deberia
  crecer como segundo sistema moderno; el camino correcto es consolidar reglas
  y flujos nuevos aqui
- `invitation_token` sirve para arrancar el flujo de invitaciones; si luego
  Vexxo necesita expiracion, reenvios, auditoria o multiples intentos, conviene
  extraer ese ciclo de vida a un modelo `AccountInvitation`
- `metadata` es util para contexto de invitacion, canal, origen o flags
  temporales de compatibilidad; no debe convertirse en una fuente informal de
  permisos o reglas de negocio
"""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from finance.accounts.domain.enums import AccountAccessMode, AccountMembershipRole

User = get_user_model()


class AccountMembership(models.Model):
    """
    Membresia de una cuenta compartida.

    Fuente de verdad para permisos de:
    - ver
    - postear transacciones
    - administrar miembros
    - administrar settings
    - ver analytics

    Mantiene compatibilidad con Account.read_only/shared_from_user (legacy)
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

    can_post_transactions = models.BooleanField(default=True)
    can_manage_members = models.BooleanField(default=False)
    can_manage_account_settings = models.BooleanField(default=False)
    can_view_analytics = models.BooleanField(default=True)

    invited_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invited_account_memberships",
    )
    invitation_token = models.UUIDField(default=uuid.uuid4, editable=False)
    invitation_sent_at = models.DateTimeField(null=True, blank=True)

    accepted_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Contexto auxiliar de invitacion o compatibilidad. No usar para permisos."),
    )

    class Meta:
        verbose_name = "Account membership"
        verbose_name_plural = "Account memberships"
        constraints = [
            models.UniqueConstraint(fields=["account", "user"], name="unique_account_membership_per_user"),
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
        return self.access_mode in {AccountAccessMode.READ_ONLY, AccountAccessMode.WATCH_ONLY}

    @property
    def is_owner(self) -> bool:
        return self.role == AccountMembershipRole.OWNER

    @property
    def is_admin_or_higher(self) -> bool:
        return self.role in {AccountMembershipRole.ADMIN, AccountMembershipRole.OWNER}

    @property
    def effective_can_post_transactions(self) -> bool:
        if self.is_read_only:
            return False
        return self.can_post_transactions

    @property
    def effective_can_manage_members(self) -> bool:
        return self.can_manage_members or self.is_admin_or_higher

    @property
    def effective_can_manage_account_settings(self) -> bool:
        return self.can_manage_account_settings or self.is_admin_or_higher

    @property
    def invitation_pending(self) -> bool:
        return self.invitation_sent_at is not None and self.accepted_at is None and self.is_active is False

    def _normalize_permissions(self) -> None:
        if self.account_id and self.user_id and getattr(self.account, "owner_id", None) == self.user_id:
            self.role = AccountMembershipRole.OWNER
            self.access_mode = AccountAccessMode.FULL

        if self.is_owner:
            self.can_post_transactions = True
            self.can_manage_members = True
            self.can_manage_account_settings = True
            self.can_view_analytics = True

        if self.is_read_only:
            self.can_post_transactions = False

        if self.is_active and self.joined_at is None:
            self.joined_at = timezone.now()

        # Si la membresia fue creada desde una invitacion y ya esta activa,
        # la aceptacion no deberia quedar indefinida.
        if self.is_active and self.invitation_sent_at and self.accepted_at is None:
            self.accepted_at = self.joined_at or timezone.now()

        if not self.is_active and self.revoked_at is None:
            self.revoked_at = timezone.now()

        if self.is_active:
            self.revoked_at = None

    def clean(self) -> None:
        super().clean()
        self._normalize_permissions()

        if self.is_read_only and self.can_post_transactions:
            raise ValidationError({"can_post_transactions": _("Read-only no puede postear transacciones.")})

        if self.role in {AccountMembershipRole.OWNER, AccountMembershipRole.ADMIN} and not self.can_view_analytics:
            raise ValidationError({"can_view_analytics": _("Owner/Admin deben poder ver analytics.")})

        if self.invited_by_id and self.user_id and self.invited_by_id == self.user_id:
            raise ValidationError({"invited_by": _("El usuario invitado no puede invitarse a si mismo.")})

        if self.accepted_at and self.invitation_sent_at and self.accepted_at < self.invitation_sent_at:
            raise ValidationError({"accepted_at": _("accepted_at no puede ser anterior a invitation_sent_at.")})

        if self.joined_at and self.accepted_at and self.joined_at < self.accepted_at:
            raise ValidationError({"joined_at": _("joined_at no puede ser anterior a accepted_at.")})

    def rotate_invitation_token(self, *, sent_at=None, commit: bool = True):
        self.invitation_token = uuid.uuid4()
        self.invitation_sent_at = sent_at or timezone.now()
        self.accepted_at = None
        self.joined_at = None
        self.revoked_at = None
        self.is_active = False
        if commit:
            self.save(
                update_fields=[
                    "invitation_token",
                    "invitation_sent_at",
                    "accepted_at",
                    "joined_at",
                    "revoked_at",
                    "is_active",
                ]
            )

    def save(self, *args, **kwargs):
        self._normalize_permissions()
        super().save(*args, **kwargs)

    def accept(self, *, accepted_at=None, joined_at=None, commit: bool = True):
        accepted_value = accepted_at or timezone.now()
        self.is_active = True
        self.revoked_at = None
        self.accepted_at = accepted_value
        self.joined_at = joined_at or accepted_value
        if commit:
            self.save(update_fields=["is_active", "revoked_at", "accepted_at", "joined_at"])

    def activate(self, *, joined_at=None, commit: bool = True):
        accepted_value = self.accepted_at or timezone.now()
        self.accept(
            accepted_at=accepted_value,
            joined_at=joined_at or self.joined_at or accepted_value,
            commit=commit,
        )

    def revoke(self, *, revoked_at=None, commit: bool = True):
        self.is_active = False
        self.revoked_at = revoked_at or timezone.now()
        if commit:
            self.save(update_fields=["is_active", "revoked_at"])
