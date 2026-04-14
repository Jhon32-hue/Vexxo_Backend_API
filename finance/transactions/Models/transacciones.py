from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class Tag(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags")
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
        indexes = [models.Index(fields=["owner", "name"])]

    def __str__(self):
        return self.name


class IncomeSource(models.Model):
    class Kind(models.TextChoices):
        SALARY = "salary", _("salario")
        BUSINESS = "business", _("negocio")
        INVESTMENT = "investment", _("inversion")
        OTHER = "other", _("otro")

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="income_sources")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.BUSINESS)
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
        indexes = [models.Index(fields=["owner", "kind"])]

    def __str__(self):
        return f"{self.name} ({self.kind})"


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
        PENDING = "pending", _("pendiente")
        POSTED = "posted", _("contabilizada")
        RECONCILED = "reconciled", _("conciliada")
        CANCELED = "canceled", _("cancelada")
        FAILED = "failed", _("fallida")

    class CreditDebitIndicator(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        DEBIT = "debit", _("debito")
        CREDIT = "credit", _("credito")

    class Rail(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        MANUAL = "manual", _("manual")
        OPEN_BANKING = "open_banking", _("open banking")
        BANK_TRANSFER = "bank_transfer", _("transferencia bancaria")
        CARD = "card", _("tarjeta")
        WALLET = "wallet", _("wallet")
        PAYMENT_NETWORK = "payment_network", _("red de pagos")
        MESSAGE = "message", _("mensaje")
        IMPORT = "import", _("importacion")
        OTHER = "other", _("otro")

    class Channel(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        MANUAL = "manual", _("manual")
        CARD_PRESENT = "card_present", _("tarjeta presente")
        ECOMMERCE = "ecommerce", _("ecommerce")
        BANK_TRANSFER = "bank_transfer", _("transferencia bancaria")
        WALLET = "wallet", _("wallet")
        SMS = "sms", _("sms")
        EMAIL = "email", _("email")
        MESSAGE_INFERRED = "message_inferred", _("mensaje inferido")
        API = "api", _("api")
        IMPORT = "import", _("importacion")
        OTHER = "other", _("otro")

    class DataOrigin(models.TextChoices):
        UNSPECIFIED = "", _("sin dato")
        MANUAL = "manual", _("manual")
        OPEN_BANKING = "open_banking", _("open banking")
        PAYMENT_NETWORK = "payment_network", _("red de pagos")
        WALLET = "wallet", _("wallet")
        MESSAGE = "message", _("mensaje")
        IMPORT = "import", _("importacion")
        INFERRED = "inferred", _("inferida")
        PAYMENT_INTENT = "payment_intent", _("payment intent")

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=16, choices=Type.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.POSTED,
        help_text=_("Estado contable de la transaccion."),
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    date = models.DateField()
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Descripcion corta canonica visible para consultas y UI."),
    )
    booking_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Momento contable reportado por la fuente cuando existe."),
    )
    value_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Momento de valor liquidado reportado por la fuente cuando existe."),
    )
    credit_debit_indicator = models.CharField(
        max_length=16,
        choices=CreditDebitIndicator.choices,
        blank=True,
        default=CreditDebitIndicator.UNSPECIFIED,
    )
    rail = models.CharField(
        max_length=32,
        choices=Rail.choices,
        blank=True,
        default=Rail.UNSPECIFIED,
        help_text=_("Rail canonico del movimiento: open_banking, wallet, card, transfer, etc."),
    )
    channel = models.CharField(
        max_length=32,
        choices=Channel.choices,
        blank=True,
        default=Channel.UNSPECIFIED,
        help_text=_("Canal canonico del movimiento: ecommerce, sms, email, api, etc."),
    )
    data_origin = models.CharField(
        max_length=32,
        choices=DataOrigin.choices,
        blank=True,
        default=DataOrigin.UNSPECIFIED,
        help_text=_("Origen y nivel de confianza del dato materializado."),
    )
    confidence_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_("Confianza de 0-100 cuando la fuente es inferida o parcialmente confiable."),
    )
    country_code = models.CharField(max_length=2, blank=True, default="")
    balance_after_transaction = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    original_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField(max_length=3, blank=True, default="")
    fx_rate = models.DecimalField(max_digits=16, decimal_places=8, null=True, blank=True)
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
    payment_intent = models.OneToOneField(
        "payment_intents.PaymentIntent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_transaction",
    )
    source = models.CharField(
        max_length=64,
        blank=True,
        default="manual",
        help_text=_("Origen: manual, ocr, api, open_finance, import, payment_intent, etc."),
    )
    provider = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Proveedor externo o fuente operativa asociada."),
    )
    external_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text=_("ID externo de la transaccion en el proveedor."),
    )
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Payload crudo de la integracion externa para trazabilidad."),
    )
    fingerprint = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text=_("Huella para deteccion de duplicados."),
    )
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    confirmed = models.BooleanField(
        default=True,
        help_text=_("Indica si la transaccion ya fue aceptada por el usuario o por una fuente confiable."),
    )
    components = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Desglose opcional: {'interest': 1000, 'principal': 9000, ...}"),
    )
    tags = models.ManyToManyField("transactions.Tag", blank=True, related_name="transactions")
    notes = models.TextField(blank=True, default="")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="splits",
        on_delete=models.CASCADE,
        help_text=_("Transaccion padre si esta es un split analitico."),
    )
    affects_balance = models.BooleanField(
        default=True,
        help_text=_("Si esta transaccion impacta o no el balance de la cuenta."),
    )
    is_reimbursable = models.BooleanField(
        default=False,
        help_text=_("Marca si este gasto deberia ser reembolsado por alguien."),
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
        help_text=_("Lista de comentarios tipo hilo asociados a la transaccion."),
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
            models.Index(fields=["owner", "rail"]),
            models.Index(fields=["owner", "channel"]),
            models.Index(fields=["owner", "fingerprint"]),
            models.Index(fields=["external_id", "provider"]),
        ]

    def __str__(self):
        return f"{self.type} {self.amount} on {self.date}"

    @property
    def is_posted(self) -> bool:
        return self.status in {self.Status.POSTED, self.Status.RECONCILED}

    @property
    def is_countable_for_ledger(self) -> bool:
        return bool(self.confirmed and self.affects_balance and self.is_posted)

    @property
    def is_split_parent(self) -> bool:
        return self.splits.exists()

    def normalize_state(self):
        if self.confirmed and self.status == self.Status.PENDING:
            self.status = self.Status.POSTED
        if self.status in {self.Status.POSTED, self.Status.RECONCILED}:
            self.confirmed = True
        if self.status in {self.Status.CANCELED, self.Status.FAILED}:
            self.affects_balance = False

    def clean(self):
        super().clean()
        self.normalize_state()
        if self.status == self.Status.RECONCILED and not self.confirmed:
            raise ValidationError(
                {"confirmed": _("Una transaccion reconciliada debe estar confirmada.")}
            )

    def save(self, *args, **kwargs):
        self.normalize_state()
        super().save(*args, **kwargs)


class ScheduledPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("pendiente")
        PAID = "paid", _("pagado")
        CANCELED = "canceled", _("cancelado")

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="scheduled_payments")
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
    tags = models.ManyToManyField("transactions.Tag", blank=True, related_name="scheduled_payments")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
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


class TransactionParticipant(models.Model):
    class Direction(models.TextChoices):
        USER_IS_CREDITOR = "user_creditor", _("El contacto me debe")
        USER_IS_DEBTOR = "user_debtor", _("Yo le debo al contacto")

    class Role(models.TextChoices):
        OWNER = "owner", _("dueno de la cuenta")
        FRIEND = "friend", _("amigo/contacto")
        EXTERNAL = "external", _("externo")

    class Status(models.TextChoices):
        ACTIVE = "active", _("activo")
        PENDING = "pending", _("pendiente")
        PARTIAL = "partial", _("parcialmente pagado")
        SETTLED = "settled", _("liquidado")
        CANCELED = "canceled", _("cancelado")

    class InviteStatus(models.TextChoices):
        NONE = "none", _("sin invitacion")
        INVITED = "invited", _("invitado")
        JOINED = "joined", _("se unio a Vexxo")

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transaction_participants")
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="participants",
    )
    linked_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions_as_contact",
        help_text=_("Usuario asociado si esta contraparte ya tiene cuenta en Vexxo."),
    )
    display_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=_("Nombre congelado del participante para historial y UI."),
    )
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    direction = models.CharField(max_length=32, choices=Direction.choices, default=Direction.USER_IS_CREDITOR)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.FRIEND)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    invite_status = models.CharField(max_length=16, choices=InviteStatus.choices, default=InviteStatus.NONE)
    share_amount = models.DecimalField(max_digits=16, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Participante de transaccion")
        verbose_name_plural = _("Participantes de transaccion")
        indexes = [
            models.Index(fields=["owner", "transaction"]),
            models.Index(fields=["owner", "contact"]),
            models.Index(fields=["owner", "direction"]),
            models.Index(fields=["contact", "status"]),
        ]

    def __str__(self):
        return f"{self.display_name or self.contact_id or 'participant'} -> {self.share_amount}"

    @property
    def pending_amount(self) -> Decimal:
        remaining = Decimal(self.share_amount or 0) - Decimal(self.paid_amount or 0)
        if remaining < 0:
            return Decimal("0.00")
        return remaining.quantize(Decimal("0.01"))

    @property
    def is_active_status(self) -> bool:
        return self.status in {self.Status.ACTIVE, self.Status.PENDING, self.Status.PARTIAL}

    @property
    def is_settled(self) -> bool:
        return self.status == self.Status.SETTLED or self.pending_amount == 0

    def normalize_state(self):
        if self.paid_amount is None:
            self.paid_amount = Decimal("0.00")
        if self.paid_amount >= self.share_amount:
            self.paid_amount = self.share_amount
            self.status = self.Status.SETTLED
        elif self.paid_amount > 0:
            self.status = self.Status.PARTIAL
        elif self.status not in {self.Status.CANCELED, self.Status.ACTIVE}:
            self.status = self.Status.ACTIVE

    def clean(self):
        super().clean()
        self.normalize_state()
        if self.contact_id and self.contact.owner_id != self.owner_id:
            raise ValidationError({"contact": _("El contacto no pertenece al owner de la transaccion.")})
        if self.transaction_id and self.transaction.owner_id != self.owner_id:
            raise ValidationError({"transaction": _("La transaccion no pertenece al owner declarado.")})

    def save(self, *args, **kwargs):
        self.normalize_state()
        if not self.display_name and self.contact_id:
            effective_name = getattr(self.contact, "effective_name", None)
            self.display_name = (
                effective_name()
                if callable(effective_name)
                else (self.contact.nickname or self.contact.name)
            )
        super().save(*args, **kwargs)

    def mark_settled(self, commit: bool = True):
        self.paid_amount = self.share_amount
        self.status = self.Status.SETTLED
        if commit:
            self.save(update_fields=["paid_amount", "status", "updated_at"])
