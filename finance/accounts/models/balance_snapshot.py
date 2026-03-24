"""
Snapshots de reconciliacion de balances.

Descripcion general:
- guarda una foto del balance cacheado frente al balance recomputado
- permite medir drift y consistencia contable de cada cuenta

Analisis detallado:
- este modelo complementa a `Account`; no reemplaza el balance operativo
- sirve para auditoria, jobs nocturnos, soporte y deteccion de deriva
- `drift`, `drift_abs` e `is_consistent` deben derivarse siempre de los
  balances comparados; por eso se normalizan al guardar
- la consistencia no se evalua por igualdad exacta, sino por un umbral pequeno
  para tolerar redondeos y diferencias menores de precision
- `source` permite saber por que canal se genero el snapshot, lo cual ayuda a
  diferenciar chequeos programados, revisiones manuales o remediaciones
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

CONSISTENCY_THRESHOLD = Decimal("0.000001")


class BalanceSnapshot(models.Model):
    """
    Snapshot para detectar drift entre cache incremental y recalc de ledger.
    """

    account = models.ForeignKey("accounts.Account", on_delete=models.CASCADE, related_name="balance_snapshots")
    as_of = models.DateTimeField(db_index=True)

    balance_cached = models.DecimalField(max_digits=18, decimal_places=6)
    balance_recomputed = models.DecimalField(max_digits=18, decimal_places=6)
    drift = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    tx_count = models.PositiveIntegerField(default=0)
    is_consistent = models.BooleanField(default=True)

    drift_abs = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("0.000000"),
        help_text="Valor absoluto del drift para filtros rapidos.",
    )
    source = models.CharField(
        max_length=32,
        default="scheduled_job",
        blank=True,
        help_text="Origen del snapshot: scheduled_job, manual_recheck, post_incident, etc.",
    )
    note = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-as_of"]
        verbose_name = "Balance snapshot"
        verbose_name_plural = "Balance snapshots"
        indexes = [
            models.Index(fields=["account", "as_of"]),
            models.Index(fields=["is_consistent", "as_of"]),
            models.Index(fields=["account", "is_consistent"]),
        ]

    def clean(self):
        super().clean()
        if self.tx_count is not None and self.tx_count < 0:
            raise ValidationError({"tx_count": "tx_count no puede ser negativo."})

    def save(self, *args, **kwargs):
        cached = Decimal(self.balance_cached or Decimal("0.0"))
        recomputed = Decimal(self.balance_recomputed or Decimal("0.0"))
        self.drift = (recomputed - cached).quantize(Decimal("0.000001"))
        self.drift_abs = abs(self.drift).quantize(Decimal("0.000001"))
        self.is_consistent = self.drift_abs <= CONSISTENCY_THRESHOLD
        super().save(*args, **kwargs)

    @property
    def drift_direction(self) -> str:
        if self.drift > 0:
            return "understated_cache"
        if self.drift < 0:
            return "overstated_cache"
        return "balanced"

    def exceeds_threshold(self, threshold: Decimal) -> bool:
        return self.drift_abs > abs(Decimal(threshold))

    def __str__(self) -> str:
        return f"Snapshot(account={self.account_id}, as_of={self.as_of}, drift={self.drift})"
