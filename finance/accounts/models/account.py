from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

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


class Currency(models.TextChoices):
    # America Latina
    COP = "COP", "Peso Colombiano"
    MXN = "MXN", "Peso Mexicano"
    ARS = "ARS", "Peso Argentino"
    CLP = "CLP", "Peso Chileno"
    PEN = "PEN", "Sol Peruano"
    BRL = "BRL", "Real Brasileño"
    PYG = "PYG", "Guaraní Paraguayo"
    UYU = "UYU", "Peso Uruguayo"
    BOB = "BOB", "Boliviano"
    CRC = "CRC", "Colón Costarricense"
    GTQ = "GTQ", "Quetzal Guatemalteco"
    DOP = "DOP", "Peso Dominicano"
    HNL = "HNL", "Lempira Hondureña"
    NIO = "NIO", "Córdoba Nicaragüense"
    PAB = "PAB", "Balboa Panameño"

    # Globales
    USD = "USD", "Dólar Americano"
    EUR = "EUR", "Euro"
    GBP = "GBP", "Libra Esterlina"
    CHF = "CHF", "Franco Suizo"
    CAD = "CAD", "Dólar Canadiense"
    AUD = "AUD", "Dólar Australiano"
    NZD = "NZD", "Dólar Neozelandés"
    JPY = "JPY", "Yen Japonés"
    CNY = "CNY", "Yuan Chino"
    INR = "INR", "Rupia India"
    KRW = "KRW", "Won Surcoreano"
    SGD = "SGD", "Dólar de Singapur"
    HKD = "HKD", "Dólar de Hong Kong"
    AED = "AED", "Dirham EAU"
    SAR = "SAR", "Riyal Saudí"


class Account(models.Model):
    """
    Cuenta financiera (ledger root).
    - Balance real proviene del ledger (transactions).
    - balance es cache incremental actualizado por use_cases/signals.
    - Social: memberships (fuente de verdad), pero mantenemos read_only/shared_from_user por compatibilidad.
    """

    # ===== Ownership =====
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=120)

    # slug opcional para URLs amigables / dedupe en UI
    slug = models.SlugField(max_length=140, blank=True, default="", db_index=True)

    type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.BANK)
    currency = models.CharField(max_length=10, choices=Currency.choices, default=Currency.COP)

    # ===== Integración / Open Finance =====
    country = models.CharField(
        max_length=2,
        blank=True,
        help_text=_("País ISO 3166-1 alpha-2, ej. CO, MX, AR."),
    )
    institution = models.CharField(
        max_length=120,
        blank=True,
        help_text=_("Banco, billetera o institución financiera."),
    )
    provider = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Proveedor externo: banco, exchange, agregador Open Finance, etc."),
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("ID externo en proveedor (Open Finance, APIs, etc.)."),
    )

    last_sync_at = models.DateTimeField(null=True, blank=True)

    class SyncStatus(models.TextChoices):
        IDLE = "idle", _("Sincronización inactiva")
        OK = "ok", _("Sincronización correcta")
        ERROR = "error", _("Error de sincronización")

    sync_status = models.CharField(max_length=16, choices=SyncStatus.choices, default=SyncStatus.IDLE)
    sync_error_message = models.CharField(max_length=255, blank=True, default="")
    allow_auto_sync = models.BooleanField(default=True)

    # ===== Balances (cache) =====
    initial_balance = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0.000000"),
        help_text=_("Saldo inicial. Puede ser negativo para crédito/préstamo."),
    )
    balance = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0.000000"),
        help_text=_("Saldo cache incremental mantenido desde el ledger."),
    )

    # Multimoneda (opcional)
    base_currency = models.CharField(
        max_length=10,
        choices=Currency.choices,
        blank=True,
        default="",
        help_text=_("Moneda base del usuario (para vistas consolidadas)."),
    )
    virtual_balance_base = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0.000000"),
        help_text=_("Saldo convertido a moneda base (si aplica)."),
    )

    # ===== Estado / visibilidad =====
    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)

    closed_at = models.DateTimeField(null=True, blank=True)
    closed_reason = models.CharField(max_length=255, blank=True, default="")

    # ===== Legacy social / observed =====
    read_only = models.BooleanField(
        default=False,
        help_text=_("Legacy: cuenta solo lectura (migrando a AccountMembership.access_mode)."),
    )
    shared_from_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shared_accounts",
        help_text=_("Legacy: usuario que compartió esta cuenta."),
    )

    # ===== Smart rules / limits =====
    monthly_expense_limit = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text=_("Límite mensual para alertas/bloqueo (opcional)."),
    )
    lock_on_limit = models.BooleanField(default=False)

    risk_level = models.CharField(max_length=16, blank=True, default="normal")
    require_2fa_for_movements = models.BooleanField(default=False)
    auto_round_savings_enabled = models.BooleanField(default=False)

    # ===== Goals =====
    goal_amount = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    goal_deadline = models.DateField(null=True, blank=True)

    # ===== Audit-lite =====
    last_activity_at = models.DateTimeField(null=True, blank=True)
    last_transaction_amount = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0.000000")
    )
    last_transaction_type = models.CharField(max_length=16, blank=True, default="")

    # ===== Timestamps =====
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Cuenta")
        verbose_name_plural = _("Cuentas")
        constraints = [
            # Dedupe razonable: un usuario no debería tener 2 cuentas con mismo nombre+moneda
            models.UniqueConstraint(
                fields=["owner", "name", "currency"],
                name="unique_account_per_user_currency",
            ),
            # Unicidad por provider/external_id si vienen informados (evita duplicar cuentas importadas)
            models.UniqueConstraint(
                fields=["owner", "provider", "external_id"],
                condition=Q(provider__gt="") & Q(external_id__gt=""),
                name="unique_account_provider_external_id_per_owner",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["owner", "archived"]),
            models.Index(fields=["owner", "type"]),
            models.Index(fields=["owner", "is_primary"]),
            models.Index(fields=["owner", "provider"]),
            models.Index(fields=["owner", "currency"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.currency}]"

    @property
    def is_closed(self) -> bool:
        return (not self.is_active) and (self.closed_at is not None)

    def clean(self) -> None:
        # Validación simple: si está cerrada, debe tener closed_at
        if not self.is_active and self.closed_at is None:
            raise ValidationError({"closed_at": _("Si is_active=False, closed_at debe estar definido.")})

        # Límite mensual no puede ser negativo si existe
        if self.monthly_expense_limit is not None and self.monthly_expense_limit < Decimal("0"):
            raise ValidationError({"monthly_expense_limit": _("El límite mensual no puede ser negativo.")})

        # Goal amount no puede ser negativo
        if self.goal_amount is not None and self.goal_amount < Decimal("0"):
            raise ValidationError({"goal_amount": _("El objetivo (goal_amount) no puede ser negativo.")})

    def save(self, *args, **kwargs):
        # Slug estable (no obligatorio)
        if self.name and not self.slug:
            base = slugify(self.name)[:120] or "account"
            # No hacemos unique global para evitar dolor; es solo para UI.
            self.slug = base
        super().save(*args, **kwargs)

    # ===== Ledger helpers (mantiene tu lógica) =====

    def transactions_qs(self):
        """
        Queryset de transacciones confirmadas + contabilizadas asociadas a esta cuenta.
        OJO: no importamos Transaction aquí para evitar ciclos; tu use_case/signals ya lo manejan.
        """
        from django.apps import apps
        Transaction = apps.get_model("transactions", "Transaction")

        # Si tienes enums en Transaction, usa los tuyos; si no, constants.
        from finance.transactions.constants import POSTED_STATUSES

        return Transaction.objects.filter(
            account=self,
            confirmed=True,
            affects_balance=True,
            status__in=POSTED_STATUSES,
        )

    def _compute_transactions_net(self) -> Decimal:
        """
        Neto del ledger (income suma, expense/transfer restan).
        Mantiene tu lógica; solo centraliza constantes.
        """
        from finance.transactions.constants import CREDIT_TYPES, DEBIT_TYPES

        net = self.transactions_qs().aggregate(
            net=Coalesce(
                models.Sum(
                    models.Case(
                        models.When(type__in=list(CREDIT_TYPES), then=models.F("amount")),
                        models.When(type__in=list(DEBIT_TYPES), then=models.F("amount") * Decimal("-1.0")),
                        default=Decimal("0.0"),
                        output_field=models.DecimalField(max_digits=24, decimal_places=6),
                    )
                ),
                Decimal("0.0"),
            )
        )["net"]
        return Decimal(net or Decimal("0.0"))

    def current_balance(self) -> Decimal:
        """
        Saldo real desde ledger completo.
        """
        return (Decimal(self.initial_balance) + self._compute_transactions_net()).quantize(Decimal("0.000001"))

    def recalc_balance(self, commit: bool = True) -> Decimal:
        """
        Recalcula el balance desde el ledger.
        Usado por reconciliación/soporte/integraciones.
        """
        new_balance = self.current_balance()
        self.balance = new_balance
        if commit:
            self.save(update_fields=["balance", "updated_at"])
        return new_balance
    def close(self, commit: bool = True) -> Decimal:
        """
        Cierra la cuenta y congela su balance.
        Idempotente: si ya esta cerrada, solo devuelve el balance.
        """
        from django.utils import timezone

        if not self.is_closed:
            self.is_active = False
            self.closed_at = timezone.now()
            if commit:
                self.save(update_fields=["is_active", "closed_at", "updated_at"])
        return self.balance
