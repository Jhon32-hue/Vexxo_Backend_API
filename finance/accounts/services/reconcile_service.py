# accounts/services/reconcile_service.py
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from finance.accounts.models.account import Account
from finance.accounts.models.balance_snapshot import BalanceSnapshot

logger = logging.getLogger(__name__)

DEFAULT_DRIFT_THRESHOLD = Decimal("0.000001")


def create_balance_snapshot(
    *,
    account: Account,
    as_of=None,
    drift_threshold: Decimal = DEFAULT_DRIFT_THRESHOLD,
    auto_repair: bool = False,
) -> BalanceSnapshot:
    """
    Crea snapshot comparando:
    - balance_cached (Account.balance)
    - balance_recomputed (Account.current_balance())

    Si auto_repair=True y drift supera threshold, hace recalc y deja el cache consistente.
    """
    as_of = as_of or timezone.now()

    with transaction.atomic():
        # Lock para evitar que un delta concurrente distorsione snapshot
        acc = Account.objects.select_for_update().get(pk=account.pk)

        cached = Decimal(acc.balance)
        recomputed = Decimal(acc.current_balance())
        drift = (recomputed - cached)

        tx_count = acc.transactions_qs().count()

        snapshot = BalanceSnapshot.objects.create(
            account=acc,
            as_of=as_of,
            balance_cached=cached,
            balance_recomputed=recomputed,
            drift=drift,
            tx_count=tx_count,
            # is_consistent se auto-calcula en model.save() si lo dejaste así
            note="auto_repair" if auto_repair else "",
        )

        # Reparación opcional
        if auto_repair and abs(drift) > drift_threshold:
            old = acc.balance
            new = acc.recalc_balance(commit=True)
            logger.warning(
                "[reconcile] auto_repair account_id=%s old_cached=%s recomputed=%s new_cached=%s drift=%s",
                acc.pk,
                old,
                recomputed,
                new,
                drift,
            )

        return snapshot
