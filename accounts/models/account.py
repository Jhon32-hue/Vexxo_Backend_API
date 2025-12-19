from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator

User = get_user_model()


class Account(models.Model):
    """
    Representa una cuenta contable del usuario:
    puede ser bancaria, tarjeta, efectivo, inversión o monedero.
    """

    TYPE_CHOICES = [
        ("cash", _("Efectivo")),
        ("bank", _("Cuenta Bancaria")),
        ("credit", _("Tarjeta de Crédito")),
        ("wallet", _("Monedero Digital")),
        ("investment", _("Cuenta de Inversión")),
        ("other", _("Otro")),
    ]

    CURRENCY_CHOICES = [
        ("COP", "Peso Colombiano"),
        ("USD", "Dólar Americano"),
        ("EUR", "Euro"),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="bank")
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default="COP")
    initial_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0.00"))]
    )
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("owner", "name", "currency")
        verbose_name = _("Cuenta")
        verbose_name_plural = _("Cuentas")

    def __str__(self):
        return f"{self.name} [{self.currency}]"

    # ----------------------------------------------------------
    # BUSINESS METHODS
    # ----------------------------------------------------------
    def transactions_qs(self):
        """Obtiene las transacciones asociadas."""
        from transactions.Models.transacciones import Transaction
        return Transaction.objects.filter(account=self, confirmed=True)

    def transactions_total(self):
        """Calcula la diferencia entre ingresos y gastos."""
        txs = self.transactions_qs()
        income = txs.filter(type="income").aggregate(models.Sum("amount"))["amount__sum"] or Decimal("0.00")
        expense = txs.filter(type="expense").aggregate(models.Sum("amount"))["amount__sum"] or Decimal("0.00")
        return income - expense

    def current_balance(self):
        """Calcula el saldo actual (inicial + ingresos - gastos)."""
        return (self.initial_balance + self.transactions_total()).quantize(Decimal("0.01"))

    def recalc_balance(self, commit=True):
        """Recalcula y sincroniza balance con transacciones confirmadas."""
        new_balance = self.current_balance()
        self.balance = new_balance
        if commit:
            self.save(update_fields=["balance"])
        return new_balance

    def close(self):
        """Cierra la cuenta y congela su balance."""
        from django.utils import timezone
        self.is_active = False
        self.closed_at = timezone.now()
        self.save(update_fields=["is_active", "closed_at"])
        return self.balance
