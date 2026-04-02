"""
Registro persistente de fallbacks del balance incremental.

Descripcion general:
- guarda evidencia cuando `accounts.signals` no puede aplicar delta
  incremental y debe recalcular saldo desde ledger

Analisis detallado:
- el fallback protege consistencia contable, pero tambien es una senal de salud
  operativa
- esta tabla permite medir frecuencia, motivos y cuentas afectadas
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models


class AccountBalanceFallback(models.Model):
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="balance_fallback_events",
    )
    transaction_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    reason = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=64, default="accounts.signals.fallback_recalc", db_index=True)
    old_state_present = models.BooleanField(default=False)
    affected_account_ids = models.JSONField(default=list, blank=True)
    old_balance = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    new_balance = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    recalculated = models.BooleanField(default=False, db_index=True)
    delta = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Account balance fallback"
        verbose_name_plural = "Account balance fallbacks"
        indexes = [
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["reason", "created_at"]),
            models.Index(fields=["recalculated", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"BalanceFallback(account={self.account_id}, tx={self.transaction_id}, reason={self.reason})"
