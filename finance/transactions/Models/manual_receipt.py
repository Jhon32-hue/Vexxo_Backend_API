from django.conf import settings
from django.db import models


class ManualTransactionReceipt(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key_hash = models.CharField(max_length=64)
    payload_hash = models.CharField(max_length=64)
    transaction = models.ForeignKey(
        "transactions.Transaction", null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["actor", "key_hash"], name="unique_manual_receipt_actor_key"
        )]
