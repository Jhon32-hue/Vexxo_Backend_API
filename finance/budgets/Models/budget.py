from django.conf import settings
from django.db import models


def default_budget_alert_thresholds():
    return [30, 50, 70, 100]


class Budget(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    month = models.CharField(max_length=7)  # YYYY-MM
    category = models.ForeignKey("categories.Category", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    alert_thresholds = models.JSONField(default=default_budget_alert_thresholds, blank=True)

    class Meta:
        unique_together = ("owner", "month", "category")

    def __str__(self) -> str:
        return f"Budget(owner={self.owner_id}, month={self.month}, category={self.category_id}, amount={self.amount})"
