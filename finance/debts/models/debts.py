from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
User = get_user_model()


class Debt(models.Model):
    """
    Representa una deuda o crédito general, con condiciones de pago.
    """
    PRIORITY_CHOICES = (
        ("low", _("baja")),
        ("medium", _("media")),
        ("high", _("alta")),
        ("urgent", _("urgente")),
    )

    STATUS_CHOICES = (
        ("active", _("activa")),
        ("closed", _("cerrada")),
        ("overdue", _("vencida")),
    )

    FREQUENCY_CHOICES = (
        ("weekly", _("semanal")),
        ("biweekly", _("quincenal")),
        ("monthly", _("mensual")),
        ("quarterly", _("trimestral")),
        ("yearly", _("anual")),
    )

    INTEREST_TYPE_CHOICES = (
        ("none", _("sin interés")),
        ("fixed", _("fijo")),
        ("variable", _("variable")),
    )

    COMPOUNDING_CHOICES = (
        ("none", _("sin capitalización")),
        ("daily", _("diaria")),
        ("monthly", _("mensual")),
        ("annually", _("anual")),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="debts")
    vendor = models.ForeignKey(
        "vendors.Vendor", null=True, blank=True, on_delete=models.SET_NULL, related_name="debts"
    )

    name = models.CharField(max_length=200)
    principal = models.DecimalField(max_digits=16, decimal_places=2)
    currency = models.CharField(max_length=10, default="COP")
    start_date = models.DateField()

    interest_rate = models.DecimalField(max_digits=8, decimal_places=4, default=0)  # 0.0200 = 2% mensual
    interest_type = models.CharField(
        max_length=16, choices=INTEREST_TYPE_CHOICES, default="none"
    )
    compounding = models.CharField(
        max_length=16, choices=COMPOUNDING_CHOICES, default="monthly"
    )

    term_months = models.PositiveIntegerField(null=True, blank=True)
    total_installments = models.PositiveIntegerField(null=True, blank=True)
    frequency = models.CharField(
        max_length=16, choices=FREQUENCY_CHOICES, default="monthly"
    )

    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default="active"
    )
    priority = models.CharField(
        max_length=8, choices=PRIORITY_CHOICES, default="medium"
    )
    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.currency})"

    @property
    def total_paid(self):
        """Suma total pagada en todas las cuotas."""
        return sum(i.paid_amount for i in self.installments.all())

    @property
    def remaining_balance(self):
        """Saldo pendiente calculado automáticamente."""
        total = sum(i.amount_due for i in self.installments.all())
        return total - self.total_paid

    def close_if_fully_paid(self):
        """Cierra la deuda si todas las cuotas están pagadas."""
        if all(i.status == "paid" for i in self.installments.all()):
            self.status = "closed"
            self.save(update_fields=["status"])


class DebtInstallment(models.Model):
    """
    Representa una cuota asociada a una deuda.
    Se enlaza con transacciones y pagos programados.
    """
    STATUS_CHOICES = (
        ("due", _("pendiente")),
        ("partial", _("parcial")),
        ("paid", _("pagada")),
        ("overdue", _("vencida")),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="installments")
    debt = models.ForeignKey(Debt, related_name="installments", on_delete=models.CASCADE)
    number = models.PositiveIntegerField()
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=16, decimal_places=2)
    principal_component = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    interest_component = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    paid_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default="due")

    # Relaciones contables
    paid_transaction = models.ForeignKey(
        "transactions.Transaction", null=True, blank=True, on_delete=models.SET_NULL, related_name="paid_installments"
    )
    payment_template = models.ForeignKey(
        "scheduled_payments.PaymentTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="debt_installments",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("debt", "number")
        ordering = ["debt_id", "number"]

    def __str__(self):
        return f"{self.debt.name} - cuota {self.number} ({self.status})"

    def mark_as_paid(self, transaction=None, amount=None, date=None):
        """
        Marca la cuota como pagada o parcialmente pagada.
        """
        if amount is None:
            amount = self.amount_due
        self.paid_amount = amount
        self.paid_transaction = transaction
        self.paid_date = date
        self.status = "paid" if amount >= self.amount_due else "partial"
        self.save()
        self.debt.close_if_fully_paid()

    @property
    def remaining_amount(self):
        return max(self.amount_due - self.paid_amount, 0)
