from django.db import models


class SharedBudgetTransactionLink(models.Model):
    shared_budget = models.ForeignKey(
        "budgets.SharedBudget",
        on_delete=models.CASCADE,
        related_name="transaction_links",
    )
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.PROTECT,
        related_name="shared_budget_links",
    )
    linked_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shared_budget_transaction_links_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("shared_budget", "transaction")
        ordering = ["-created_at", "-id"]


class SharedBudgetTemplateLink(models.Model):
    shared_budget = models.ForeignKey(
        "budgets.SharedBudget",
        on_delete=models.CASCADE,
        related_name="template_links",
    )
    payment_template = models.ForeignKey(
        "scheduled_payments.PaymentTemplate",
        on_delete=models.PROTECT,
        related_name="shared_budget_links",
    )
    linked_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shared_budget_template_links_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("shared_budget", "payment_template")
        ordering = ["-created_at", "-id"]
