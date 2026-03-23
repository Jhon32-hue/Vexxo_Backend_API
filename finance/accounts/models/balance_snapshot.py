from __future__ import annotations

from decimal import Decimal
from django.db import models


class BalanceSnapshot(models.Model):
    """
    Snapshot para detectar drift entre cache incremental y recalc de ledger.

    Útil para:
    - jobs nocturnos de reconciliación
    - auditoría
    - alertas cuando drift supera threshold
    """

    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="balance_snapshots")
    as_of = models.DateTimeField(db_index=True)

    balance_cached = models.DecimalField(max_digits=18, decimal_places=6)
    balance_recomputed = models.DecimalField(max_digits=18, decimal_places=6)
    drift = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    tx_count = models.PositiveIntegerField(default=0)
    is_consistent = models.BooleanField(default=True)

    # Extras pro (opcionales, pero útiles)
    drift_abs = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("0.000000"),
        help_text="Valor absoluto del drift para filtros rápidos."
    )
    note = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-as_of"]
        indexes = [
            models.Index(fields=["account", "as_of"]),
            models.Index(fields=["is_consistent", "as_of"]),
            models.Index(fields=["account", "is_consistent"]),
        ]

    def save(self, *args, **kwargs):
        # Normalizamos drift_abs e is_consistent
        self.drift_abs = abs(Decimal(self.drift or Decimal("0.0")))
        self.is_consistent = (self.drift_abs == Decimal("0.0"))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Snapshot(account={self.account_id}, as_of={self.as_of}, drift={self.drift})"