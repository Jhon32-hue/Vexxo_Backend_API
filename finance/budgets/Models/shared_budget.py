from django.conf import settings
from django.db import models

from .budget import default_budget_alert_thresholds


class SharedBudget(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_shared_budgets",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="shared_budgets",
    )
    name = models.CharField(max_length=160)
    month = models.CharField(max_length=7)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    alert_thresholds = models.JSONField(default=default_budget_alert_thresholds, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("team", "month", "name")
        ordering = ["-month", "name", "-id"]

    def __str__(self) -> str:
        return f"SharedBudget(team={self.team_id}, month={self.month}, name={self.name})"
