"""
Servicio de reconciliacion contable para cuentas financieras.

Descripcion general:
- compara el balance cacheado de `Account` contra el recomputo desde ledger
- crea snapshots operativos y publica eventos de reconciliacion del modulo

Analisis detallado:
- este servicio es el punto canonico para generar `BalanceSnapshot`, ya sea
  desde API, comandos, jobs nocturnos o soporte
- si detecta drift, publica un evento especifico para que alertas,
  observabilidad o integraciones reaccionen
- opcionalmente puede reparar el cache local cuando el drift supera el umbral
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from finance.accounts.domain.events import AccountDomainEventTypes, build_account_snapshot_payload
from finance.accounts.models.account import Account
from finance.accounts.models.balance_snapshot import BalanceSnapshot
from finance.accounts.services.outbox_service import publish_account_event

logger = logging.getLogger(__name__)

DEFAULT_DRIFT_THRESHOLD = Decimal("0.000001")


def create_balance_snapshot(
    *,
    account: Account,
    as_of=None,
    drift_threshold: Decimal = DEFAULT_DRIFT_THRESHOLD,
    source: str = "scheduled_job",
    auto_repair: bool = False,
) -> BalanceSnapshot:
    """
    Crea snapshot comparando cache vs ledger y publica eventos del resultado.
    """
    as_of = as_of or timezone.now()

    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)

        cached = Decimal(acc.balance)
        recomputed = Decimal(acc.current_balance())
        drift = recomputed - cached
        tx_count = acc.transactions_qs().count()

        snapshot = BalanceSnapshot.objects.create(
            account=acc,
            as_of=as_of,
            balance_cached=cached,
            balance_recomputed=recomputed,
            drift=drift,
            tx_count=tx_count,
            source=(source or "scheduled_job")[:32],
            note="auto_repair" if auto_repair else "",
        )

        publish_account_event(
            account=acc,
            event_type=AccountDomainEventTypes.ACCOUNT_SNAPSHOT_CREATED,
            payload=build_account_snapshot_payload(
                snapshot=snapshot,
                change="snapshot_created",
                drift_threshold=drift_threshold,
                extra={"auto_repair": auto_repair},
            ),
            metadata={"source": "accounts.services.reconcile_service"},
        )

        if not snapshot.is_consistent:
            publish_account_event(
                account=acc,
                event_type=AccountDomainEventTypes.ACCOUNT_DRIFT_DETECTED,
                payload=build_account_snapshot_payload(
                    snapshot=snapshot,
                    change="drift_detected",
                    drift_threshold=drift_threshold,
                    extra={"auto_repair": auto_repair},
                ),
                metadata={"source": "accounts.services.reconcile_service"},
            )

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
