# transactions/Models/transacciones.py
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


# ========== TAGS ==========

class Tag(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tags",
    )
    name = models.CharField(max_length=64)
    is_recurring = models.BooleanField(
        default=False,
        help_text=_("Marca si este tag suele representar un gasto o ingreso recurrente."),
    )
    color = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text=_("Color opcional para UI (hex o tailwind key)."),
    )

    class Meta:
        unique_together = ("owner", "name")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["owner", "name"]),
        ]

    def __str__(self):
        return self.name


# ========== INCOME SOURCES ==========

class IncomeSource(models.Model):
    class Kind(models.TextChoices):
        SALARY = "salary", _("salario")
        BUSINESS = "business", _("negocio")
        INVESTMENT = "investment", _("inversión")
        OTHER = "other", _("otro")

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="income_sources",
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.BUSINESS,
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="income_sources",
    )

    class Meta:
        unique_together = ("owner", "name")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["owner", "kind"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.kind})"


# ========== TRANSACTIONS ==========

class Transaction(models.Model):
    class Type(models.TextChoices):
        EXPENSE = "expense", _("gasto")
        INCOME = "income", _("ingreso")
        TRANSFER = "transfer", _("transferencia")

    class Priority(models.TextChoices):
        LOW = "low", _("baja")
        MEDIUM = "medium", _("media")
        HIGH = "high", _("alta")
        URGENT = "urgent", _("urgente")

    class Status(models.TextChoices):
        PENDING = "pending", _("pendiente")        # autorizada, aún no contable
        POSTED = "posted", _("contabilizada")      # impacta el balance
        RECONCILED = "reconciled", _("conciliada") # confirmada con el banco
        CANCELED = "canceled", _("cancelada")
        FAILED = "failed", _("fallida")

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    type = models.CharField(
        max_length=16,
        choices=Type.choices,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.POSTED,
        help_text=_("Estado contable de la transacción."),
    )

    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
    )
    date = models.DateField()

    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    category = models.ForeignKey(
        "categories.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    income_source = models.ForeignKey(
        "transactions.IncomeSource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    debt = models.ForeignKey(
        "debts.Debt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    installment = models.ForeignKey(
        "debts.DebtInstallment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )
    scheduled_payment = models.ForeignKey(
        "transactions.ScheduledPayment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
    )

    # Fuente y metadatos para integraciones (manual / whatsapp / ocr / api / open_finance)
    source = models.CharField(
        max_length=64,
        blank=True,
        default="manual",
        help_text=_("Origen de la transacción: manual, whatsapp, ocr, api, open_finance, etc."),
    )
    provider = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Proveedor externo: banco, exchange, agregador de Open Finance, etc."),
    )
    external_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text=_("ID externo de la transacción en el proveedor."),
    )
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Payload crudo proveniente de integraciones externas para trazabilidad."),
    )
    fingerprint = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text=_("Huella para detección de duplicados (hash de amount+date+vendor+ref)."),
    )

    priority = models.CharField(
        max_length=8,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    confirmed = models.BooleanField(
        default=True,
        help_text=_("Indica si la transacción ya fue confirmada por el usuario."),
    )
    components = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Desglose opcional: {'interest': 1000, 'principal': 9000, ...}"),
    )
    tags = models.ManyToManyField(
        "transactions.Tag",
        blank=True,
        related_name="transactions",
    )
    notes = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["owner", "date"]),
            models.Index(fields=["owner", "account", "date"]),
            models.Index(fields=["owner", "type", "date"]),
            models.Index(fields=["owner", "fingerprint"]),
            models.Index(fields=["external_id", "provider"]),
        ]

    def __str__(self):
        return f"{self.type} {self.amount} on {self.date}"

    @property
    def is_posted(self) -> bool:
        return self.status in {self.Status.POSTED, self.Status.RECONCILED}


# ========== SCHEDULED PAYMENTS ==========

class ScheduledPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("pendiente")
        PAID = "paid", _("pagado")
        CANCELED = "canceled", _("cancelado")

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="scheduled_payments",
    )
    name = models.CharField(max_length=140)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    due_date = models.DateField()

    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_payments",
    )
    category = models.ForeignKey(
        "categories.Category",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_payments",
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_payments",
    )
    debt = models.ForeignKey(
        "debts.Debt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_payments",
    )
    installment = models.ForeignKey(
        "debts.DebtInstallment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scheduled_payments",
    )

    priority = models.CharField(
        max_length=8,
        choices=Transaction.Priority.choices,
        default=Transaction.Priority.MEDIUM,
    )
    tags = models.ManyToManyField(
        "transactions.Tag",
        blank=True,
        related_name="scheduled_payments",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "-id"]
        indexes = [
            models.Index(fields=["owner", "due_date"]),
            models.Index(fields=["owner", "status"]),
        ]

    def __str__(self):
        return f"{self.name} due {self.due_date}"
