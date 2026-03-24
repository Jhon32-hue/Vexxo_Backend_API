"""
Modelos principales de cuentas financieras.

Descripcion general:
- define la entidad `Account` con metadata operativa, social y multimoneda
- modela estados de vida de una cuenta
- incluye permisos de acceso compartido mediante `AccountAccess`

Analisis detallado:
- La cuenta concentra integracion externa, visibilidad, sincronizacion, limites, metas, gamificacion y auditoria
- `balance` funciona como cache operativo y `recalc_balance()` permite
  recalcularlo desde ledger cuando se necesita consistencia fuerte
- `virtual_balance_base`, `last_fx_rate` y `last_fx_at` guardan la ultima
  conversion aplicada a la cuenta, pero no consultan APIs FX por si solos
- `set_virtual_balance_base()` asume que otro servicio ya resolvio la tasa
  correcta y viene a persistir el resultado consolidado
- `provider`, `external_id`, `sync_status` y `provider_metadata` preparan el
  modelo para open finance o exchanges sin obligar a tener esa integracion hoy
- `AccountAccess` convive con `AccountMembership`, lo que sugiere una capa
  social en evolucion entre mecanismos legacy y mas modernos
- la cuenta ya contiene suficiente metadata para interoperar con workers,
  integraciones externas y pipelines event-driven sin reestructurar el modelo
- helpers como `link_external_account()` o `schedule_next_sync()` permiten
  preparar el backend para syncs gestionados fuera del monolito
- metodos de ciclo de sync como `mark_sync_running`, `mark_sync_ok`,
  `mark_sync_error` y `mark_sync_stale` preparan el modelo para workers y
  callbacks externos sin exponer demasiada logica en las vistas

Que se puede hacer despues:
- crear un servicio de consolidacion que tome la ultima tasa vigente desde
  `ExchangeRate` y actualice `virtual_balance_base`
- separar parte de la logica operativa a servicios de dominio si el modelo
  crece demasiado, manteniendo aqui solo invariantes y helpers criticos
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from finance.fx.models import Currency

User = get_user_model()


class AccountType(models.TextChoices):
    CASH = "cash", _("Efectivo")
    BANK = "bank", _("Cuenta Bancaria")
    CREDIT = "credit", _("Tarjeta de Crédito")
    WALLET = "wallet", _("Monedero Digital")
    INVESTMENT = "investment", _("Cuenta de Inversión")
    SAVINGS = "savings", _("Cuenta de Ahorros")
    LOAN = "loan", _("Préstamo / Crédito")
    BROKERAGE = "brokerage", _("Broker / Trading")
    RETIREMENT = "retirement", _("Retiro / Pensión")
    CRYPTO = "crypto", _("Cripto")
    PREPAID = "prepaid", _("Cuenta Prepago")
    JOINT = "joint", _("Cuenta Compartida")
    CUSTODIAL = "custodial", _("Cuenta Custodia")
    OTHER = "other", _("Otro")


class AccountRole(models.TextChoices):
    SPENDING = "spending", _("Gasto diario")
    EMERGENCY = "emergency", _("Fondo de emergencia")
    GOAL_VAULT = "goal_vault", _("Bóveda de meta")
    SHARED_POOL = "shared_pool", _("Pool compartido")
    INVEST_PORTFOLIO = "invest_portfolio", _("Portafolio de inversión")
    CREDIT_LINE = "credit_line", _("Línea de crédito")
    OBSERVED_ONLY = "observed_only", _("Solo observación")


class AccountOwnership(models.TextChoices):
    OWNED = "owned", _("Propia")
    SHARED = "shared", _("Compartida")
    OBSERVED = "observed", _("Observada")


class AccountStatus(models.TextChoices):
    ACTIVE = "active", _("Activa")
    ARCHIVED = "archived", _("Archivada")
    CLOSED = "closed", _("Cerrada")
    FROZEN = "frozen", _("Congelada")


class SyncStatus(models.TextChoices):
    IDLE = "idle", _("Sincronización inactiva")
    OK = "ok", _("Sincronización correcta")
    ERROR = "error", _("Error de sincronización")
    RUNNING = "running", _("Sincronizando")
    STALE = "stale", _("Datos desactualizados")


class GoalStrategy(models.TextChoices):
    NONE = "none", _("Sin estrategia")
    WEEKLY = "weekly", _("Aporte semanal")
    MONTHLY = "monthly", _("Aporte mensual")
    ROUND_UP = "round_up", _("Redondeo automático")
    PERCENT_OF_INCOME = "percent_income", _("Porcentaje de ingresos")
    SMART = "smart", _("Estrategia inteligente")


class RiskLevel(models.TextChoices):
    LOW = "low", _("Bajo")
    NORMAL = "normal", _("Normal")
    HIGH = "high", _("Alto")


class SharedScopeType(models.TextChoices):
    NONE = "none", _("Ninguno")
    GROUP = "group", _("Grupo")
    GOAL = "goal", _("Meta compartida")
    CIRCLE = "circle", _("Círculo financiero")
    TEAM = "team", _("Equipo")


class AccountVisibility(models.TextChoices):
    PRIVATE = "private", _("Privada")
    INTERNAL_SHARED = "internal_shared", _("Compartida internamente")
    PUBLIC_PROFILE = "public_profile", _("Visible en perfil público")


class Account(models.Model):
    """
    Cuenta avanzada de Vexxo.
    Diseñada para:
    - multimoneda
    - social finance
    - open finance metadata
    - límites y reglas
    - auditoría embebida
    - gamificación
    """

    # Identidad base
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
        help_text=_("País ISO 3166-1 alpha-2 de la cuenta."),
    )

    institution = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=_("Banco, billetera o institución asociada."),
    )

    description = models.CharField(max_length=255, blank=True, default="")
    color = models.CharField(max_length=16, blank=True, default="")
    icon = models.CharField(max_length=32, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)

    # Integración / Open Finance
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
        help_text=_("Últimos dígitos o máscara visible."),
    )
    external_type = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Tipo externo reportado por el proveedor."),
    )

    sync_status = models.CharField(
        max_length=16,
        choices=SyncStatus.choices,
        default=SyncStatus.IDLE,
        db_index=True,
    )
    sync_error_message = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    allow_auto_sync = models.BooleanField(default=True)

    last_sync_at = models.DateTimeField(null=True, blank=True)
    next_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_duration_ms = models.PositiveIntegerField(default=0)
    sync_attempts = models.PositiveIntegerField(default=0)
    sync_cursor = models.CharField(max_length=255, blank=True, default="")
    provider_metadata = models.JSONField(default=dict, blank=True)

    # Saldos y consolidación
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
        help_text=_("Última tasa FX usada para virtual_balance_base."),
    )

    last_fx_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp de la tasa FX usada."),
    )

    # Estado y cierre
    is_primary = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)

    closed_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.CharField(max_length=255, blank=True, default="")

    frozen_at = models.DateTimeField(null=True, blank=True)
    frozen_reason = models.CharField(max_length=255, blank=True, default="")

    # Scope social / compartido
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
        help_text=_("ID del grupo/meta/círculo/equipo asociado."),
    )

    # Límites y seguridad
    monthly_expense_limit = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )

    daily_expense_limit = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )

    lock_on_limit = models.BooleanField(default=False)

    risk_level = models.CharField(
        max_length=16,
        choices=RiskLevel.choices,
        default=RiskLevel.NORMAL,
    )

    require_2fa_for_movements = models.BooleanField(default=False)
    auto_round_savings_enabled = models.BooleanField(default=False)

    # Objetivos avanzados
    goal_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )

    goal_deadline = models.DateField(
        null=True,
        blank=True,
    )

    goal_strategy = models.CharField(
        max_length=24,
        choices=GoalStrategy.choices,
        default=GoalStrategy.NONE,
    )

    auto_contribute_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )

    auto_contribute_percent = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_("Porcentaje 0-100 para estrategia de aporte."),
    )

    # Gamificación
    xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)
    streak_days = models.PositiveIntegerField(default=0)
    last_streak_at = models.DateField(null=True, blank=True)
    badges = models.JSONField(default=list, blank=True)

    # Auditoría embebida
    last_activity_at = models.DateTimeField(null=True, blank=True)
    last_transaction_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    last_transaction_type = models.CharField(
        max_length=16,
        blank=True,
        default="",
    )

    last_balance_change_at = models.DateTimeField(null=True, blank=True)
    last_balance_change_reason = models.CharField(max_length=64, blank=True, default="")
    last_sync_status_at = models.DateTimeField(null=True, blank=True)

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

    def clean(self):
        super().clean()

        if self.type not in {AccountType.CREDIT, AccountType.LOAN} and self.initial_balance < Decimal("0.00"):
            raise ValidationError(
                {"initial_balance": _("Solo cuentas de crédito o préstamo pueden iniciar con saldo negativo.")}
            )

        if self.auto_contribute_percent is not None:
            if self.auto_contribute_percent < Decimal("0.00") or self.auto_contribute_percent > Decimal("100.000"):
                raise ValidationError(
                    {"auto_contribute_percent": _("Debe estar entre 0 y 100.")}
                )

        if self.shared_scope_type != SharedScopeType.NONE and not self.shared_scope_id:
            raise ValidationError(
                {"shared_scope_id": _("Es requerido cuando la cuenta tiene un scope compartido.")}
            )

        if self.shared_scope_type == SharedScopeType.NONE:
            self.shared_scope_id = ""

        if self.status == AccountStatus.CLOSED and not self.closed_at:
            self.closed_at = timezone.now()

        if self.status == AccountStatus.FROZEN and not self.frozen_at:
            self.frozen_at = timezone.now()

        if self.external_id and not self.provider:
            raise ValidationError(
                {"provider": _("provider es requerido cuando external_id tiene valor.")}
            )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.owner_id}-{self.name}-{self.currency}")[:140]

        if not self.base_currency and getattr(self.owner, "preferred_currency", None):
            self.base_currency = self.owner.preferred_currency

        super().save(*args, **kwargs)

    def set_as_primary(self):
        with transaction.atomic():
            Account.objects.filter(
                owner=self.owner,
                is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)

            if not self.is_primary:
                self.is_primary = True
                self.save(update_fields=["is_primary", "updated_at"])

    def active_memberships_qs(self):
        return self.memberships.filter(is_active=True).select_related("user", "invited_by")

    def has_active_collaborators(self) -> bool:
        return self.active_memberships_qs().exclude(user_id=self.owner_id).exists()

    def ensure_owner_membership(self, commit: bool = True):
        from finance.accounts.domain.enums import AccountAccessMode, AccountMembershipRole
        from finance.accounts.models.membership import AccountMembership

        membership, created = AccountMembership.objects.get_or_create(
            account=self,
            user=self.owner,
            defaults={
                "role": AccountMembershipRole.OWNER,
                "access_mode": AccountAccessMode.FULL,
                "can_post_transactions": True,
                "can_manage_members": True,
                "can_manage_account_settings": True,
                "can_view_analytics": True,
                "is_active": True,
            },
        )
        if not created:
            changed = False
            expected = {
                "role": AccountMembershipRole.OWNER,
                "access_mode": AccountAccessMode.FULL,
                "can_post_transactions": True,
                "can_manage_members": True,
                "can_manage_account_settings": True,
                "can_view_analytics": True,
                "is_active": True,
            }
            for field, value in expected.items():
                if getattr(membership, field) != value:
                    setattr(membership, field, value)
                    changed = True
            if changed and commit:
                membership.save()
        return membership

    def mark_sync_running(self, commit: bool = True):
        self.sync_status = SyncStatus.RUNNING
        self.last_sync_status_at = timezone.now()
        if commit:
            self.save(update_fields=["sync_status", "last_sync_status_at", "updated_at"])

    def mark_sync_ok(self, commit: bool = True, duration_ms: int = 0):
        now = timezone.now()
        self.sync_status = SyncStatus.OK
        self.sync_error_message = ""
        self.last_sync_at = now
        self.last_sync_status_at = now
        self.sync_attempts = 0
        self.last_sync_duration_ms = max(0, int(duration_ms))
        if commit:
            self.save(
                update_fields=[
                    "sync_status",
                    "sync_error_message",
                    "last_sync_at",
                    "last_sync_status_at",
                    "sync_attempts",
                    "last_sync_duration_ms",
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
                    "updated_at",
                ]
            )

    def mark_sync_stale(self, commit: bool = True):
        self.sync_status = SyncStatus.STALE
        self.last_sync_status_at = timezone.now()
        if commit:
            self.save(update_fields=["sync_status", "last_sync_status_at", "updated_at"])

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
        fx_at: Optional[timezone.datetime] = None,
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
        if provider_metadata:
            self.provider_metadata = dict(provider_metadata)
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
                    "next_sync_at",
                    "sync_status",
                    "last_sync_status_at",
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

    def transactions_qs(self):
        from finance.transactions.Models.transacciones import Transaction

        return Transaction.objects.filter(
            account=self,
            confirmed=True,
        )

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


class AccountAccessRole(models.TextChoices):
    OWNER = "owner", _("Owner")
    ADMIN = "admin", _("Admin")
    CONTRIBUTOR = "contributor", _("Contributor")
    VIEWER = "viewer", _("Viewer")


class AccountAccess(models.Model):
    """
    Sharing avanzado para cuentas:
    - cuentas observadas
    - cuentas compartidas
    - pools de viaje
    - metas grupales
    """

    account = models.ForeignKey(
        Account,
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
