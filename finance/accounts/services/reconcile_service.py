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
- `snapshot.is_consistent` expresa una consistencia de precision pequena del
  modelo; `drift_threshold` expresa el umbral material que importa para
  reaccion operativa y auto-repair
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from finance.accounts.domain.events import (
    AccountDomainEventTypes,
    build_account_lifecycle_payload,
    build_account_snapshot_payload,
)
from finance.accounts.models.account import Account, AccountVerificationLevel
from finance.accounts.models.balance_snapshot import BalanceSnapshot
from finance.accounts.services.outbox_service import publish_account_balance_updated, publish_account_event

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
    drift_threshold = abs(Decimal(drift_threshold))

    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)

        cached = Decimal(acc.balance)
        recomputed = Decimal(acc.current_balance())
        drift = recomputed - cached
        tx_count = acc.transactions_qs().count()
        material_drift = abs(drift) > drift_threshold

        snapshot = BalanceSnapshot.objects.create(
            account=acc,
            as_of=as_of,
            balance_cached=cached,
            balance_recomputed=recomputed,
            drift=drift,
            tx_count=tx_count,
            source=(source or "scheduled_job")[:32],
            note="auto_repair_requested" if auto_repair else "",
        )

        account_updates: dict[str, object] = {}
        if snapshot.is_consistent:
            account_updates["last_consistent_snapshot_at"] = as_of
            account_updates["verification_level"] = AccountVerificationLevel.RECONCILED
            account_updates["confidence_score"] = max(int(acc.confidence_score or 0), 90)
        if material_drift:
            account_updates["last_drift_detected_at"] = as_of
            account_updates["verification_level"] = (
                AccountVerificationLevel.EXTERNALLY_VERIFIED
                if acc.has_external_link
                else AccountVerificationLevel.SELF_DECLARED
            )
            account_updates["confidence_score"] = min(int(acc.confidence_score or 100), 45)
        if account_updates:
            Account.objects.filter(pk=acc.pk).update(**account_updates)
            for field, value in account_updates.items():
                setattr(acc, field, value)

        publish_account_event(
            account=acc,
            event_type=AccountDomainEventTypes.ACCOUNT_SNAPSHOT_CREATED,
            payload=build_account_snapshot_payload(
                snapshot=snapshot,
                change="snapshot_created",
                drift_threshold=drift_threshold,
                extra={
                    "auto_repair": auto_repair,
                    "material_drift": material_drift,
                },
            ),
            metadata={"source": "accounts.services.reconcile_service"},
        )

        if material_drift:
            publish_account_event(
                account=acc,
                event_type=AccountDomainEventTypes.ACCOUNT_DRIFT_DETECTED,
                payload=build_account_snapshot_payload(
                    snapshot=snapshot,
                    change="drift_detected",
                    drift_threshold=drift_threshold,
                    extra={
                        "auto_repair": auto_repair,
                        "material_drift": material_drift,
                    },
                ),
                metadata={"source": "accounts.services.reconcile_service"},
            )

        if auto_repair and material_drift:
            old_balance = acc.balance
            new_balance = acc.recalc_balance(commit=True, reason="auto_repair_reconcile")
            snapshot.note = "auto_repaired"
            snapshot.save(update_fields=["note"])

            publish_account_balance_updated(
                account=acc,
                old_balance=old_balance,
                new_balance=new_balance,
                reason="auto_repair_reconcile",
                metadata={"source": "accounts.services.reconcile_service"},
            )
            publish_account_event(
                account=acc,
                event_type=AccountDomainEventTypes.ACCOUNT_RECALCULATED,
                payload=build_account_lifecycle_payload(
                    account=acc,
                    change="recalculated",
                    extra={
                        "reason": "auto_repair_reconcile",
                        "old_balance": str(old_balance),
                        "new_balance": str(new_balance),
                        "snapshot_id": str(snapshot.pk),
                    },
                ),
                metadata={"source": "accounts.services.reconcile_service"},
            )
            logger.warning(
                "[reconcile] auto_repair account_id=%s old_cached=%s recomputed=%s new_cached=%s drift=%s threshold=%s",
                acc.pk,
                old_balance,
                recomputed,
                new_balance,
                drift,
                drift_threshold,
            )

        return snapshot
