from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()

# TAGS
class Tag(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=64)
    is_recurring = models.BooleanField(default=False)
    color = models.CharField(max_length=16, blank=True, default="")

    class Meta:
        unique_together = ("owner", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name

# INCOME SOURCE
class IncomeSource(models.Model):
    KIND_CHOICES = (
        ("salary", _("salario")),
        ("business", _("negocio")),
        ("investment", _("inversión")),
        ("other", _("otro")),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="income_sources")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="business")
    vendor = models.ForeignKey(
        "vendors.Vendor", null=True, blank=True, on_delete=models.SET_NULL, related_name="income_sources"
    )

    class Meta:
        unique_together = ("owner", "name")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.kind})"

# TRANSACTIONS
class Transaction(models.Model):
    TYPE_CHOICES = (
        ("expense", _("gasto")),
        ("income", _("ingreso")),
        ("transfer", _("transferencia")),
    )
    PRIORITY_CHOICES = (
        ("low", _("baja")),
        ("medium", _("media")),
        ("high", _("alta")),
        ("urgent", _("urgente")),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    date = models.DateField()

    account = models.ForeignKey(
        "accounts.Account", on_delete=models.PROTECT, related_name="transactions"
    )
    category = models.ForeignKey(
        "categories.Category", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    vendor = models.ForeignKey(
        "vendors.Vendor", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    income_source = models.ForeignKey(
        "transactions.IncomeSource", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    debt = models.ForeignKey(
        "debts.Debt", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    installment = models.ForeignKey(
        "debts.DebtInstallment", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    scheduled_payment = models.ForeignKey(
        "transactions.ScheduledPayment", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )

    source = models.CharField(max_length=64, blank=True, default="manual")  # whatsapp|ocr|manual|api
    priority = models.CharField(max_length=8, choices=PRIORITY_CHOICES, default="medium")
    confirmed = models.BooleanField(default=True)
    components = models.JSONField(default=dict, blank=True)  # p.ej. {"interest":1000, "principal":9000}
    tags = models.ManyToManyField("transactions.Tag", blank=True, related_name="transactions")
    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.type} {self.amount} on {self.date}"

# SCHEDULED PAYMENTS
class ScheduledPayment(models.Model):
    STATUS_CHOICES = (
        ("pending", _("pendiente")),
        ("paid", _("pagado")),
        ("canceled", _("cancelado")),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="scheduled_payments")
    name = models.CharField(max_length=140)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    due_date = models.DateField()

    account = models.ForeignKey("accounts.Account", null=True, blank=True, on_delete=models.SET_NULL, related_name="scheduled_payments")
    category = models.ForeignKey("categories.Category", null=True, blank=True, on_delete=models.SET_NULL, related_name="scheduled_payments")
    vendor = models.ForeignKey("vendors.Vendor", null=True, blank=True, on_delete=models.SET_NULL, related_name="scheduled_payments")
    debt = models.ForeignKey("debts.Debt", null=True, blank=True, on_delete=models.SET_NULL, related_name="scheduled_payments")
    installment = models.ForeignKey("debts.DebtInstallment", null=True, blank=True, on_delete=models.SET_NULL, related_name="scheduled_payments")

    priority = models.CharField(max_length=8, choices=Transaction.PRIORITY_CHOICES, default="medium")
    tags = models.ManyToManyField("transactions.Tag", blank=True, related_name="scheduled_payments")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "-id"]

    def __str__(self):
        return f"{self.name} due {self.due_date}"
