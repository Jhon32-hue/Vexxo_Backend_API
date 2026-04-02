"""
Comportamientos internos del agregado `Account`.

Descripcion general:
- separa la logica operativa del modelo principal por responsabilidades:
  salud, validacion, membresias, sincronizacion, lifecycle y balance

Analisis detallado:
- `Account` sigue siendo el agregado publico, pero estos mixins concentran las
  mutaciones y propiedades derivadas para evitar que `account.py` crezca como
  archivo unico
- aqui vive la logica que debe seguir siendo cohesionada al agregado y no a la
  capa HTTP
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .account_enums import (
    AccountDataOrigin,
    AccountSourcePriority,
    AccountStatus,
    AccountType,
    AccountVerificationLevel,
    SharedScopeType,
    SyncStatus,
)


class AccountHealthMixin:
    @property
    def is_closed(self) -> bool:
        return self.status == AccountStatus.CLOSED

    @property
    def is_frozen(self) -> bool:
        return self.status == AccountStatus.FROZEN

    @property
    def is_active(self) -> bool:
        return self.status == AccountStatus.ACTIVE

    @property
    def has_external_link(self) -> bool:
        return bool(self.provider and self.external_id)

    @property
    def sync_health(self) -> str:
        if not self.has_external_link:
            return "disconnected"
        if self.sync_status == SyncStatus.ERROR:
            return "error"
        if self.sync_status == SyncStatus.STALE:
            return "stale"
        if self.sync_status == SyncStatus.RUNNING:
            return "syncing"
        if self.sync_status == SyncStatus.OK:
            return "healthy"
        return "idle"

    @property
    def balance_health(self) -> str:
        recently_repaired = (
            self.last_balance_change_reason == "auto_repair_reconcile"
            and self.last_balance_change_at
            and self.last_balance_change_at >= timezone.now() - timedelta(days=7)
        )
        if recently_repaired:
            return "repaired_recently"
        if self.last_drift_detected_at and (
            not self.last_consistent_snapshot_at
            or self.last_drift_detected_at > self.last_consistent_snapshot_at
        ):
            return "drift_detected"
        if self.last_consistent_snapshot_at:
            return "healthy"
        return "never_reconciled"

    @property
    def membership_health(self) -> str:
        memberships = getattr(self, "_prefetched_objects_cache", {}).get("memberships")
        memberships = list(self.memberships.all()) if memberships is None else list(memberships)

        active_owner = any(m.user_id == self.owner_id and m.is_active for m in memberships)
        if not active_owner:
            return "owner_missing_membership"

        stale_threshold = timezone.now() - timedelta(days=14)
        if any(
            (
                (m.current_invitation and m.current_invitation.is_expired)
                or (
                    m.invitation_sent_at
                    and m.invitation_sent_at < stale_threshold
                    and not m.is_active
                    and m.accepted_at is None
                )
            )
            for m in memberships
        ):
            return "stale_invites"

        if any(m.revoked_at and m.is_active for m in memberships):
            return "revoked_active_conflict"

        return "healthy"

    @property
    def integration_health(self) -> str:
        if not self.has_external_link:
            return "disconnected"
        if self.sync_status == SyncStatus.ERROR:
            return "sync_failing"
        if self.sync_status == SyncStatus.STALE:
            return "external_link_stale"
        if not self.last_sync_at:
            return "never_synced"
        if self.last_sync_at >= timezone.now() - timedelta(days=7):
            return "recently_synced"
        return "external_link_stale"

    @property
    def account_operational_health(self) -> str:
        if self.membership_health in {"owner_missing_membership", "revoked_active_conflict"}:
            return "attention_required"
        if self.balance_health == "drift_detected":
            return "attention_required"
        if self.integration_health == "sync_failing":
            return "attention_required"
        if (
            self.membership_health == "stale_invites"
            or self.balance_health == "repaired_recently"
            or self.integration_health in {"never_synced", "external_link_stale"}
        ):
            return "monitoring"
        return "healthy"


class AccountValidationMixin:
    def clean(self):
        super().clean()

        if self.type not in {AccountType.CREDIT, AccountType.LOAN} and self.initial_balance < Decimal("0.00"):
            raise ValidationError(
                {"initial_balance": _("Solo cuentas de credito o prestamo pueden iniciar con saldo negativo.")}
            )

        if self.auto_contribute_percent is not None and (
            self.auto_contribute_percent < Decimal("0.00") or self.auto_contribute_percent > Decimal("100.000")
        ):
            raise ValidationError({"auto_contribute_percent": _("Debe estar entre 0 y 100.")})

        if self.shared_scope_type != SharedScopeType.NONE and not self.shared_scope_id:
            raise ValidationError({"shared_scope_id": _("Es requerido cuando la cuenta tiene un scope compartido.")})

        if self.shared_scope_type == SharedScopeType.NONE:
            self.shared_scope_id = ""

        if self.status == AccountStatus.CLOSED and not self.closed_at:
            self.closed_at = timezone.now()

        if self.status == AccountStatus.FROZEN and not self.frozen_at:
            self.frozen_at = timezone.now()

        if self.external_id and not self.provider:
            raise ValidationError({"provider": _("provider es requerido cuando external_id tiene valor.")})

        if self.confidence_score < 0 or self.confidence_score > 100:
            raise ValidationError({"confidence_score": _("confidence_score debe estar entre 0 y 100.")})

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        normalized_update_fields = set(update_fields) if update_fields is not None else None

        if not self.slug:
            self.slug = slugify(f"{self.owner_id}-{self.name}-{self.currency}")[:140]
            if normalized_update_fields is not None:
                normalized_update_fields.add("slug")

        if not self.base_currency and getattr(self.owner, "preferred_currency", None):
            self.base_currency = self.owner.preferred_currency
            if normalized_update_fields is not None:
                normalized_update_fields.add("base_currency")

        if self.pk:
            self.account_version = max(1, int(self.account_version or 0) + 1)
            if normalized_update_fields is not None:
                normalized_update_fields.add("account_version")
        else:
            self.account_version = max(1, int(self.account_version or 1))

        if normalized_update_fields is not None:
            kwargs["update_fields"] = list(normalized_update_fields)

        super().save(*args, **kwargs)

    def set_as_primary(self):
        with transaction.atomic():
            type(self).objects.filter(owner=self.owner, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
            if not self.is_primary:
                self.is_primary = True
                self.save(update_fields=["is_primary", "updated_at"])


class AccountMembershipMixin:
    def active_memberships_qs(self):
        return self.memberships.filter(is_active=True).select_related("user", "invited_by")

    def has_active_collaborators(self) -> bool:
        return self.active_memberships_qs().exclude(user_id=self.owner_id).exists()

    def ensure_owner_membership(self, commit: bool = True):
        from finance.accounts.domain.enums import AccountAccessMode, AccountMembershipRole
        from finance.accounts.models.membership import AccountMembership

        defaults = {
            "role": AccountMembershipRole.OWNER,
            "access_mode": AccountAccessMode.FULL,
            "can_post_transactions": True,
            "can_manage_members": True,
            "can_manage_account_settings": True,
            "can_view_analytics": True,
            "is_active": True,
        }
        membership, created = AccountMembership.objects.get_or_create(
            account=self,
            user=self.owner,
            defaults=defaults,
        )
        if not created:
            changed = False
            for field, value in defaults.items():
                if getattr(membership, field) != value:
                    setattr(membership, field, value)
                    changed = True
            if changed and commit:
                membership.save()
        return membership


class AccountSyncMixin:
    def mark_sync_running(self, commit: bool = True):
        self.sync_status = SyncStatus.RUNNING
        self.last_sync_status_at = timezone.now()
        if commit:
            self.save(update_fields=["sync_status", "last_sync_status_at", "sync_runtime", "updated_at"])

    def mark_sync_ok(self, commit: bool = True, duration_ms: int = 0):
        now = timezone.now()
        self.sync_status = SyncStatus.OK
        self.sync_error_message = ""
        self.last_sync_at = now
        self.last_sync_status_at = now
        self.sync_attempts = 0
        self.last_sync_duration_ms = max(0, int(duration_ms))
        if self.has_external_link:
            self.verification_level = AccountVerificationLevel.EXTERNALLY_VERIFIED
            if self.data_origin == AccountDataOrigin.MANUAL:
                self.data_origin = AccountDataOrigin.SYNCED
            self.source_priority = AccountSourcePriority.PROVIDER
            self.confidence_score = max(int(self.confidence_score or 0), 80)
        if commit:
            self.save(
                update_fields=[
                    "sync_status",
                    "sync_error_message",
                    "last_sync_at",
                    "last_sync_status_at",
                    "sync_attempts",
                    "last_sync_duration_ms",
                    "sync_runtime",
                    "verification_level",
                    "data_origin",
                    "source_priority",
                    "confidence_score",
                    "updated_at",
                ]
            )

    def mark_sync_error(self, message: str = "", commit: bool = True):
        self.sync_status = SyncStatus.ERROR
        self.sync_error_message = (message or "")[:255]
        self.last_sync_status_at = timezone.now()
        self.sync_attempts = int(self.sync_attempts or 0) + 1
        if commit:
            self.save(
                update_fields=[
                    "sync_status",
                    "sync_error_message",
                    "last_sync_status_at",
                    "sync_attempts",
                    "sync_runtime",
                    "updated_at",
                ]
            )

    def mark_sync_stale(self, commit: bool = True):
        self.sync_status = SyncStatus.STALE
        self.last_sync_status_at = timezone.now()
        if commit:
            self.save(update_fields=["sync_status", "last_sync_status_at", "sync_runtime", "updated_at"])

    def touch_activity(self, event_name: str = "", commit: bool = True):
        self.last_activity_at = timezone.now()
        if event_name:
            self.last_balance_change_reason = event_name[:64]
        if commit:
            self.save(update_fields=["last_activity_at", "last_balance_change_reason", "updated_at"])

    def set_virtual_balance_base(
        self,
        base_currency: str,
        fx_rate: Decimal,
        fx_at: Optional[datetime] = None,
        commit: bool = True,
    ):
        if fx_rate <= Decimal("0"):
            raise ValidationError({"last_fx_rate": _("La tasa FX debe ser mayor que cero.")})

        fx_at = fx_at or timezone.now()
        self.base_currency = base_currency
        self.last_fx_rate = fx_rate
        self.last_fx_at = fx_at
        self.virtual_balance_base = (self.balance * fx_rate).quantize(Decimal("0.01"))

        if commit:
            self.save(
                update_fields=[
                    "base_currency",
                    "last_fx_rate",
                    "last_fx_at",
                    "virtual_balance_base",
                    "updated_at",
                ]
            )

    def link_external_account(
        self,
        *,
        provider: str,
        external_id: str,
        external_type: str = "",
        external_mask: str = "",
        provider_metadata: dict | None = None,
        next_sync_at=None,
        commit: bool = True,
    ):
        provider_value = (provider or "").strip()[:64]
        external_id_value = (external_id or "").strip()[:255]
        if not provider_value:
            raise ValidationError({"provider": _("provider es requerido para vincular una cuenta externa.")})
        if not external_id_value:
            raise ValidationError({"external_id": _("external_id es requerido para vincular una cuenta externa.")})

        self.provider = provider_value
        self.external_id = external_id_value
        self.external_type = (external_type or "").strip()[:64]
        self.external_mask = (external_mask or "").strip()[:16]
        if self.data_origin == AccountDataOrigin.MANUAL:
            self.data_origin = AccountDataOrigin.SYNCED
        self.source_priority = AccountSourcePriority.PROVIDER
        self.confidence_score = max(int(self.confidence_score or 0), 70)
        if provider_metadata:
            self.provider_metadata = dict(provider_metadata)
        self.sync_runtime = {}
        if next_sync_at is not None:
            self.next_sync_at = next_sync_at
        self.sync_status = SyncStatus.IDLE
        self.last_sync_status_at = timezone.now()

        if commit:
            self.save(
                update_fields=[
                    "provider",
                    "external_id",
                    "external_type",
                    "external_mask",
                    "provider_metadata",
                    "sync_runtime",
                    "next_sync_at",
                    "sync_status",
                    "last_sync_status_at",
                    "data_origin",
                    "source_priority",
                    "confidence_score",
                    "updated_at",
                ]
            )

    def unlink_external_account(self, *, clear_metadata: bool = False, commit: bool = True):
        self.provider = ""
        self.external_id = ""
        self.external_type = ""
        self.external_mask = ""
        self.sync_status = SyncStatus.IDLE
        self.sync_error_message = ""
        self.sync_cursor = ""
        self.next_sync_at = None
        self.last_sync_status_at = timezone.now()
        self.sync_runtime = {}
        if clear_metadata:
            self.provider_metadata = {}

        if commit:
            self.save(
                update_fields=[
                    "provider",
                    "external_id",
                    "external_type",
                    "external_mask",
                    "sync_status",
                    "sync_error_message",
                    "sync_cursor",
                    "next_sync_at",
                    "last_sync_status_at",
                    "provider_metadata",
                    "sync_runtime",
                    "updated_at",
                ]
            )

    def schedule_next_sync(self, *, run_at=None, delay_minutes: int = 30, commit: bool = True):
        target = run_at or (timezone.now() + timedelta(minutes=max(1, int(delay_minutes))))
        self.next_sync_at = target
        self.last_sync_status_at = timezone.now()
        if self.has_external_link and self.sync_status == SyncStatus.IDLE:
            self.sync_status = SyncStatus.STALE

        if commit:
            self.save(update_fields=["next_sync_at", "last_sync_status_at", "sync_status", "updated_at"])
        return target


class AccountLifecycleMixin:
    def freeze(self, reason: str = "", commit: bool = True):
        self.status = AccountStatus.FROZEN
        self.frozen_at = timezone.now()
        self.frozen_reason = (reason or "")[:255]
        if commit:
            self.save(update_fields=["status", "frozen_at", "frozen_reason", "updated_at"])

    def unfreeze(self, commit: bool = True):
        self.status = AccountStatus.ACTIVE
        self.frozen_at = None
        self.frozen_reason = ""
        if commit:
            self.save(update_fields=["status", "frozen_at", "frozen_reason", "updated_at"])

    def archive(self, commit: bool = True):
        self.archived = True
        self.status = AccountStatus.ARCHIVED
        self.is_primary = False
        if commit:
            self.save(update_fields=["archived", "status", "is_primary", "updated_at"])

    def unarchive(self, commit: bool = True):
        self.archived = False
        if self.status == AccountStatus.ARCHIVED:
            self.status = AccountStatus.ACTIVE
        if commit:
            self.save(update_fields=["archived", "status", "updated_at"])

    def close(self, commit: bool = True, reason: str = "") -> Decimal:
        if self.is_closed:
            return self.balance

        self.status = AccountStatus.CLOSED
        self.is_primary = False
        self.closed_at = timezone.now()
        self.closed_reason = (reason or "")[:255]

        if commit:
            self.save(update_fields=["status", "is_primary", "closed_at", "closed_reason", "updated_at"])

        return self.balance


class AccountBalanceMixin:
    def transactions_qs(self):
        from finance.transactions.Models.transacciones import Transaction

        return Transaction.objects.filter(account=self, confirmed=True)

    def _compute_transactions_net(self) -> Decimal:
        qs = self.transactions_qs()
        income = qs.filter(type="income").aggregate(models.Sum("amount"))["amount__sum"] or Decimal("0.00")
        expense = qs.filter(type="expense").aggregate(models.Sum("amount"))["amount__sum"] or Decimal("0.00")
        return income - expense

    def current_balance(self) -> Decimal:
        return (self.initial_balance + self._compute_transactions_net()).quantize(Decimal("0.01"))

    def recalc_balance(self, commit: bool = True, reason: str = "recalc") -> Decimal:
        new_balance = self.current_balance()
        self.balance = new_balance
        self.last_balance_change_at = timezone.now()
        self.last_balance_change_reason = (reason or "")[:64]
        if commit:
            self.save(
                update_fields=[
                    "balance",
                    "last_balance_change_at",
                    "last_balance_change_reason",
                    "updated_at",
                ]
            )
        return new_balance

    def create_balance_snapshot(self, **kwargs):
        from finance.accounts.services.reconcile_service import create_balance_snapshot

        return create_balance_snapshot(account=self, **kwargs)
