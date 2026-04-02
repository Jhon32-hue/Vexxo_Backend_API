"""
Observabilidad persistente de fallbacks contables.

Descripcion general:
- registra eventos cuando el balance incremental debe caer a recalculo
  completo desde ledger
"""

from __future__ import annotations

from decimal import Decimal

from finance.accounts.models import AccountBalanceFallback


def record_account_balance_fallback(
    *,
    account=None,
    transaction_id=None,
    reason: str,
    source: str = "accounts.signals.fallback_recalc",
    old_state_present: bool,
    affected_account_ids=None,
    old_balance=None,
    new_balance=None,
    recalculated: bool,
    metadata: dict | None = None,
):
    old_decimal = None if old_balance is None else Decimal(str(old_balance))
    new_decimal = None if new_balance is None else Decimal(str(new_balance))
    delta = Decimal("0.000000")
    if old_decimal is not None and new_decimal is not None:
        delta = (new_decimal - old_decimal).quantize(Decimal("0.000001"))

    return AccountBalanceFallback.objects.create(
        account=account,
        transaction_id=str(transaction_id or "")[:64],
        reason=(reason or "")[:64],
        source=(source or "")[:64],
        old_state_present=bool(old_state_present),
        affected_account_ids=list(affected_account_ids or []),
        old_balance=old_decimal,
        new_balance=new_decimal,
        recalculated=bool(recalculated),
        delta=delta,
        metadata=metadata or {},
    )
