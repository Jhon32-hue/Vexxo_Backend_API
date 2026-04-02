"""
Compatibilidad legacy para acceso compartido a cuentas.

Descripcion general:
- conserva el modelo historico `AccountAccess` mientras el sharing moderno se
  consolida sobre `AccountMembership`

Analisis detallado:
- no es la fuente canonica de permisos compartidos
- debe mantenerse estable para lectura o migraciones, pero el crecimiento
  funcional del dominio debe ocurrir en `membership.py`
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class AccountAccessRole(models.TextChoices):
    OWNER = "owner", _("Owner")
    ADMIN = "admin", _("Admin")
    CONTRIBUTOR = "contributor", _("Contributor")
    VIEWER = "viewer", _("Viewer")


class AccountAccess(models.Model):
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="access_entries",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="account_access_entries",
    )
    role = models.CharField(
        max_length=16,
        choices=AccountAccessRole.choices,
        default=AccountAccessRole.VIEWER,
        db_index=True,
    )
    can_spend = models.BooleanField(default=False)
    can_edit_limits = models.BooleanField(default=False)
    can_invite = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    can_view_balance = models.BooleanField(default=True)
    can_view_transactions = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="granted_account_accesses",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Acceso a cuenta")
        verbose_name_plural = _("Accesos a cuentas")
        constraints = [
            models.UniqueConstraint(
                fields=["account", "user"],
                name="unique_account_access",
            )
        ]
        indexes = [
            models.Index(fields=["user", "role"]),
            models.Index(fields=["account", "role"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.account_id} ({self.role})"

    def _assert_legacy_write_allowed(self) -> None:
        if bool(getattr(settings, "ACCOUNTS_ACCOUNT_ACCESS_LEGACY_WRITES_ENABLED", False)):
            return
        if self._state.adding:
            raise ValidationError(
                {"detail": "AccountAccess esta en retiro. Usa AccountMembership para nuevos accesos."}
            )
        persisted = type(self).objects.filter(pk=self.pk).values("is_active", "revoked_at").first()
        if persisted is None:
            raise ValidationError(
                {"detail": "AccountAccess esta en retiro. Usa AccountMembership para nuevos accesos."}
            )
        only_deactivating = (
            persisted["is_active"] != self.is_active
            and persisted["is_active"] is True
            and self.is_active is False
        )
        revocation_changed = persisted["revoked_at"] != self.revoked_at
        if not (only_deactivating and revocation_changed):
            raise ValidationError(
                {"detail": "AccountAccess es solo lectura. Migra o administra permisos desde AccountMembership."}
            )

    def save(self, *args, **kwargs):
        self._assert_legacy_write_allowed()
        super().save(*args, **kwargs)

    def accept(self, commit: bool = True):
        self.accepted_at = timezone.now()
        self.is_active = True
        if commit:
            self.save(update_fields=["accepted_at", "is_active"])

    def revoke(self, commit: bool = True):
        self.revoked_at = timezone.now()
        self.is_active = False
        if commit:
            self.save(update_fields=["revoked_at", "is_active"])
