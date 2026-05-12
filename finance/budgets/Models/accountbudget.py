from django.conf import settings
from django.db import models


class AccountBudget(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    month = models.CharField(max_length=7)
    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        unique_together = ("owner", "month", "account")

    def __str__(self) -> str:
        return f"AccountBudget(owner={self.owner_id}, month={self.month}, account={self.account_id}, amount={self.amount})"
