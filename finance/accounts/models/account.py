"""
Modelo principal de cuentas financieras.

La entidad `Account` mantiene la superficie publica del dominio, mientras que
la logica operativa se reparte en mixins y modelos auxiliares para reducir el
acoplamiento del archivo principal.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from finance.fx.models import Currency

from .account_enums import (
    AccountDataOrigin,
    AccountOwnership,
    AccountRole,
    AccountSensitivityLevel,
    AccountSourcePriority,
    AccountStatus,
    AccountType,
    AccountVerificationLevel,
    AccountVisibility,
    GoalStrategy,
    RiskLevel,
    SharedScopeType,
    SyncStatus,
)
from .account_mixins import (
    AccountBalanceMixin,
    AccountHealthMixin,
    AccountLifecycleMixin,
    AccountMembershipMixin,
    AccountSyncMixin,
    AccountValidationMixin,
)

User = get_user_model()


class Account(
    AccountHealthMixin,
    AccountValidationMixin,
    AccountMembershipMixin,
    AccountSyncMixin,
    AccountLifecycleMixin,
    AccountBalanceMixin,
    models.Model,
):
    """
    Cuenta avanzada de Vexxo.
    Disenada para:
    - multimoneda
    - social finance
    - open finance metadata
    - limites y reglas
    - auditoria embebida
    - gamificacion
    """

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="accounts",
        db_index=True,
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, blank=True, default="")
    type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.BANK,
        db_index=True,
    )
    role = models.CharField(
        max_length=24,
        choices=AccountRole.choices,
        default=AccountRole.SPENDING,
        db_index=True,
    )
    ownership = models.CharField(
        max_length=16,
        choices=AccountOwnership.choices,
        default=AccountOwnership.OWNED,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
        db_index=True,
    )
    visibility = models.CharField(
        max_length=20,
        choices=AccountVisibility.choices,
        default=AccountVisibility.PRIVATE,
        db_index=True,
    )
    currency = models.CharField(
        max_length=10,
        choices=Currency.choices,
        default=Currency.COP,
        db_index=True,
    )
    country = models.CharField(
        max_length=2,
        blank=True,
        default="",
        help_text=_("Pais ISO 3166-1 alpha-2 de la cuenta."),
    )
    institution = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=_("Banco, billetera o institucion asociada."),
    )
    description = models.CharField(max_length=255, blank=True, default="")
    color = models.CharField(max_length=16, blank=True, default="")
    icon = models.CharField(max_length=32, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)

    provider = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Proveedor externo / agregador / exchange."),
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Identificador externo de la cuenta."),
    )
    external_mask = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text=_("Ultimos digitos o mascara visible."),
    )
    external_type = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Tipo externo reportado por el proveedor."),
    )
    data_origin = models.CharField(
        max_length=16,
        choices=AccountDataOrigin.choices,
        default=AccountDataOrigin.MANUAL,
        db_index=True,
        help_text=_("Origen principal del dato de la cuenta."),
    )
    verification_level = models.CharField(
        max_length=24,
        choices=AccountVerificationLevel.choices,
        default=AccountVerificationLevel.SELF_DECLARED,
        db_index=True,
        help_text=_("Nivel de verificacion del dato financiero de esta cuenta."),
    )
    source_priority = models.CharField(
        max_length=20,
        choices=AccountSourcePriority.choices,
        default=AccountSourcePriority.USER_DECLARED,
        help_text=_("Prioridad de la fuente cuando hay conflicto entre dato manual y externo."),
    )
    sensitivity_level = models.CharField(
        max_length=16,
        choices=AccountSensitivityLevel.choices,
        default=AccountSensitivityLevel.NORMAL,
        help_text=_("Clasificacion de sensibilidad del dato para gobierno y acceso."),
    )
    confidence_score = models.PositiveSmallIntegerField(
        default=50,
        help_text=_("Confianza del dato de 0 a 100."),
    )

    sync_status = models.CharField(
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.IDLE,
        db_index=True,
    )
    sync_error_message = models.CharField(max_length=255, blank=True, default="")
    allow_auto_sync = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    next_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_duration_ms = models.PositiveIntegerField(default=0)
    sync_attempts = models.PositiveIntegerField(default=0)
    sync_cursor = models.CharField(max_length=255, blank=True, default="")
    provider_metadata = models.JSONField(default=dict, blank=True)
    sync_runtime = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Estado interno del lifecycle de sync. No exponer como metadata de proveedor."),
    )

    initial_balance = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    balance = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Saldo actual cacheado y recalculable desde ledger."),
    )
    base_currency = models.CharField(
        max_length=10,
        choices=Currency.choices,
        blank=True,
        default="",
        help_text=_("Moneda base del usuario para vistas consolidadas."),
    )
    virtual_balance_base = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Saldo convertido a la moneda base del usuario."),
    )
    last_fx_rate = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text=_("Ultima tasa FX usada para virtual_balance_base."),
    )
    last_fx_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp de la tasa FX usada."),
    )

    is_primary = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.CharField(max_length=255, blank=True, default="")
    frozen_at = models.DateTimeField(null=True, blank=True)
    frozen_reason = models.CharField(max_length=255, blank=True, default="")

    read_only = models.BooleanField(default=False)
    shared_from_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shared_accounts",
    )
    shared_scope_type = models.CharField(
        max_length=16,
        choices=SharedScopeType.choices,
        default=SharedScopeType.NONE,
        db_index=True,
    )
    shared_scope_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text=_("ID del grupo/meta/circulo/equipo asociado."),
    )

    monthly_expense_limit = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    daily_expense_limit = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    lock_on_limit = models.BooleanField(default=False)
    risk_level = models.CharField(
        max_length=16,
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL,
    )
    require_2fa_for_movements = models.BooleanField(default=False)
    auto_round_savings_enabled = models.BooleanField(default=False)

    goal_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    goal_deadline = models.DateField(null=True, blank=True)
    goal_strategy = models.CharField(
        max_length=24,
        choices=GoalStrategy.choices,
        default=GoalStrategy.NONE,
    )
    auto_contribute_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    auto_contribute_percent = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_("Porcentaje 0-100 para estrategia de aporte."),
    )

    xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)
    streak_days = models.PositiveIntegerField(default=0)
    last_streak_at = models.DateField(null=True, blank=True)
    badges = models.JSONField(default=list, blank=True)

    last_activity_at = models.DateTimeField(null=True, blank=True)
    last_transaction_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    last_transaction_type = models.CharField(max_length=16, blank=True, default="")
    last_balance_change_at = models.DateTimeField(null=True, blank=True)
    last_balance_change_reason = models.CharField(max_length=64, blank=True, default="")
    last_sync_status_at = models.DateTimeField(null=True, blank=True)
    last_domain_event_at = models.DateTimeField(null=True, blank=True)
    last_consistent_snapshot_at = models.DateTimeField(null=True, blank=True)
    last_drift_detected_at = models.DateTimeField(null=True, blank=True)
    account_version = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Cuenta")
        verbose_name_plural = _("Cuentas")
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name", "currency"],
                name="unique_account_per_user_currency",
            ),
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(is_primary=True) & Q(status=AccountStatus.ACTIVE),
                name="unique_primary_active_account_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "type"]),
            models.Index(fields=["owner", "role"]),
            models.Index(fields=["owner", "archived"]),
            models.Index(fields=["owner", "provider"]),
            models.Index(fields=["owner", "shared_scope_type", "shared_scope_id"]),
            models.Index(fields=["owner", "sync_status"]),
            models.Index(fields=["external_id"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.currency}]"
