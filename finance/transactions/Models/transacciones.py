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
        PENDING = "pending", _("pendiente")        # importada / por confirmar
        POSTED = "posted", _("contabilizada")      # impacta el balance
        RECONCILED = "reconciled", _("conciliada") # matcheada con banco
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

    # Fuente e integraciones
    source = models.CharField(
        max_length=64,
        blank=True,
        default="manual",
        help_text=_("Origen: manual, whatsapp, ocr, api, open_finance, import, etc."),
    )
    provider = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Proveedor externo: banco, exchange, agregador Open Finance, etc."),
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
        help_text=_("Payload crudo de la integración externa para trazabilidad."),
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

    # Split / reembolso / comentarios
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="splits",
        on_delete=models.CASCADE,
        help_text=_("Transacción padre si esta es un split analítico."),
    )
    affects_balance = models.BooleanField(
        default=True,
        help_text=_("Si esta transacción impacta o no el balance de la cuenta."),
    )
    is_reimbursable = models.BooleanField(
        default=False,
        help_text=_("Marca si este gasto debería ser reembolsado por alguien."),
    )
    reimbursed = models.BooleanField(
        default=False,
        help_text=_("Indica si el reembolso ya fue registrado completamente."),
    )
    reimbursement_transaction = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="reimburses",
        on_delete=models.SET_NULL,
        help_text=_("Ingreso que representa el reembolso de este gasto."),
    )
    comments = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Lista de comentarios tipo hilo asociados a la transacción."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["owner", "date"]),
            models.Index(fields=["owner", "account", "date"]),
            models.Index(fields=["owner", "type", "date"]),
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["owner", "fingerprint"]),
            models.Index(fields=["external_id", "provider"]),
        ]

    def __str__(self):
        return f"{self.type} {self.amount} on {self.date}"

    @property
    def is_posted(self) -> bool:
        return self.status in {self.Status.POSTED, self.Status.RECONCILED}

    @property
    def is_split_parent(self) -> bool:
        return self.splits.exists()


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


# ========== PARTICIPANTES (split entre personas) ==========

class TransactionParticipant(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", _("dueño de la cuenta")
        FRIEND = "friend", _("amigo/contacto")
        EXTERNAL = "external", _("externo")

    class Status(models.TextChoices):
        PENDING = "pending", _("pendiente")
        PARTIAL = "partial", _("parcialmente pagado")
        SETTLED = "settled", _("liquidado")

    class InviteStatus(models.TextChoices):
        NONE = "none", _("sin invitación")
        INVITED = "invited", _("invitado")
        JOINED = "joined", _("se unió a Mindwallet")

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="transaction_participants",
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="participants",
    )

    linked_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions_as_contact",
        help_text=_("Usuario asociado si tiene cuenta en Mindwallet."),
    )

    display_name = models.CharField(
        max_length=120,
        help_text=_("Nombre o apodo del participante (\"Carlos\", \"Roomie\", etc.)."),
    )
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")

    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.FRIEND,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    invite_status = models.CharField(
        max_length=16,
        choices=InviteStatus.choices,
        default=InviteStatus.NONE,
    )

    share_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        help_text=_("Parte del gasto que le corresponde."),
    )
    paid_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Cuánto ha pagado ya."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Participante de transacción")
        verbose_name_plural = _("Participantes de transacción")

    def __str__(self):
        return f"{self.display_name} -> {self.share_amount}"

    @property
    def pending_amount(self) -> Decimal:
        return self.share_amount - self.paid_amount
