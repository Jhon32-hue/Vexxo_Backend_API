from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

User = get_user_model()


class AccountType(models.TextChoices):
    CASH = "cash", _("Efectivo")
    BANK = "bank", _("Cuenta Bancaria")
    CREDIT = "credit", _("Tarjeta de Crédito")
    WALLET = "wallet", _("Monedero Digital")
    INVESTMENT = "investment", _("Cuenta de Inversión")
    OTHER = "other", _("Otro")


class Currency(models.TextChoices):
    COP = "COP", "Peso Colombiano"
    USD = "USD", "Dólar Americano"
    EUR = "EUR", "Euro"


class Account(models.Model):
    """
    Representa una fuente de dinero del usuario:
    bancos, tarjetas, efectivo, wallets, brókers, etc.
    Es la entidad base del ledger de Mindwallet.
    """

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    name = models.CharField(max_length=120)

    type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.BANK,
    )
    currency = models.CharField(
        max_length=10,
        choices=Currency.choices,
        default=Currency.COP,
    )

    institution = models.CharField(
        max_length=120,
        blank=True,
        help_text=_("Banco, billetera o institución financiera asociada."),
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("ID externo de la cuenta en el proveedor (Open Finance, API externas etc.)."),
    )
    last_sync_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Última sincronización con el proveedor externo."),
    )

    initial_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Saldo inicial al momento de crear la cuenta en Mindwallet."),
    )
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Saldo actual calculado a partir del ledger de transacciones."),
    )

    is_active = models.BooleanField(default=True)
    is_primary = models.BooleanField(
        default=False,
        help_text=_("Indica si es la cuenta principal del usuario para reportes."),
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Nombre único por usuario+moneda 
            models.UniqueConstraint(
                fields=["owner", "name", "currency"],
                name="unique_account_per_user_currency",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["owner", "type"]),
        ]
        verbose_name = _("Cuenta")
        verbose_name_plural = _("Cuentas")

    def __str__(self):
        return f"{self.name} [{self.currency}]"

    @property
    def is_closed(self) -> bool:
        return not self.is_active and self.closed_at is not None

    # ========== BUSINESS METHODS ==========

    def transactions_qs(self):
        """
        Queryset de transacciones 'postadas' (confirmadas) asociadas
        a esta cuenta. El modelo Transaction debe tener un campo
        direction/type y un flag de estado.
        """
        from transactions.Models.transacciones import Transaction

        return Transaction.objects.filter(
            account=self,
            confirmed=True,  
        )

    def _compute_transactions_net(self) -> Decimal:
        """
        Calcula ingresos - gastos a partir de las transacciones confirmadas.
        Supone que Transaction tiene un campo 'type' con valores
        'income' y 'expense'.
        """
        qs = self.transactions_qs()
        income = (
            qs.filter(type="income").aggregate(models.Sum("amount"))["amount__sum"]
            or Decimal("0.00")
        )
        expense = (
            qs.filter(type="expense").aggregate(models.Sum("amount"))["amount__sum"]
            or Decimal("0.00")
        )
        return income - expense

    def current_balance(self) -> Decimal:
        """
        Calcula el saldo actual como:
        initial_balance + (ingresos - gastos)

        OJO: esto recalcula desde el ledger. Para endpoints
        de lectura normalmente usaremos el campo 'balance'
        ya actualizado por señales (signals) para evitar recálculos
        pesados en listas grandes de múltiples cuentas.
        """
        return (self.initial_balance + self._compute_transactions_net()).quantize(
            Decimal("0.01")
        )

    def recalc_balance(self, commit: bool = True) -> Decimal:
        """
        Recalcula el balance desde transacciones confirmadas y
        opcionalmente persiste el resultado.

        Este es el que deben usar las integraciones o procesos
        batch (jobs) o signals tras cambios en Transaction.
        """
        new_balance = self.current_balance()
        self.balance = new_balance
        if commit:
            self.save(update_fields=["balance", "updated_at"])
        return new_balance

    def close(self, commit: bool = True) -> Decimal:
        """
        Cierra la cuenta y congela su balance.
        Idempotente: si ya está cerrada, solo devuelve el balance.
        """
        from django.utils import timezone

        if not self.is_closed:
            self.is_active = False
            self.closed_at = timezone.now()
            if commit:
                self.save(update_fields=["is_active", "closed_at", "updated_at"])
        return self.balance
