"""
Signals de consistencia contable para accounts.

Descripcion general:
- escucha cambios sobre transacciones y mantiene el balance cacheado de
  `Account` sincronizado con el ledger
- emite eventos de dominio cuando hay cambios relevantes de balance

Analisis detallado:
- el flujo principal usa deltas incrementales para evitar recalculos completos
- cuando no se puede calcular el delta con seguridad, se hace fallback a
  `recalc_balance()` y aun asi se publica el evento `accounts.balance.updated.v1`
- esto mantiene alineados dashboards, alertas, notificaciones y futuros
  consumidores en Pub/Sub o workers externos

Que se puede hacer despues:
- agregar mas telemetria por motivo de fallback
- mover ciertos handlers a consumidores asinc si el trafico sube mucho
"""

from __future__ import annotations

import logging

from django.apps import apps
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from finance.accounts.domain.enums import BalanceChangeReason
from finance.accounts.models.account import Account
from finance.accounts.services.account_balance_fallback_service import record_account_balance_fallback
from finance.accounts.services.outbox_service import publish_account_balance_updated
from finance.accounts.use_cases import (
    TransactionBalanceState,
    apply_transaction_balance_change,
    apply_transaction_balance_delete,
)

logger = logging.getLogger(__name__)

Transaction = apps.get_model("transactions", "Transaction")


@receiver(pre_save, sender=Transaction)
def store_old_transaction_state(sender, instance, **kwargs):
    """
    Guarda snapshot previo para delta incremental.
    """
    if not instance.pk:
        instance._old_balance_state = None
        return

    old = Transaction.objects.filter(pk=instance.pk).first()
    if not old:
        instance._old_balance_state = None
        return

    instance._old_balance_state = TransactionBalanceState(
        tx_id=getattr(old, "pk", None),
        account_id=getattr(old, "account_id", None),
        tx_type=getattr(old, "type", None),
        amount=getattr(old, "amount", None),
        status=getattr(old, "status", None),
        confirmed=getattr(old, "confirmed", None),
        affects_balance=getattr(old, "affects_balance", None),
    )


@receiver(post_save, sender=Transaction)
def update_account_balance_on_transaction_save(sender, instance, created, **kwargs):
    old_state = getattr(instance, "_old_balance_state", None)

    if created:
        reason = BalanceChangeReason.TX_CREATED
    elif old_state and old_state.account_id != instance.account_id:
        reason = BalanceChangeReason.TX_MOVED
    else:
        reason = BalanceChangeReason.TX_UPDATED

    if (not created) and old_state is None:
        logger.warning("[accounts] No old_state para tx_id=%s. Fallback recalc.", instance.pk)
        _fallback_recalc(instance, reason=BalanceChangeReason.TX_FALLBACK_RECALC)
        return

    changes = apply_transaction_balance_change(instance, old_state=old_state, reason=reason)
    if not changes:
        logger.debug("[accounts] tx_id=%s sin cambio de balance (%s)", instance.pk, reason)


@receiver(post_delete, sender=Transaction)
def update_account_balance_on_transaction_delete(sender, instance, **kwargs):
    changes = apply_transaction_balance_delete(instance, reason=BalanceChangeReason.TX_DELETED)
    if not changes:
        logger.debug("[accounts] tx_id=%s delete sin efecto contable", instance.pk)


def _fallback_recalc(tx, *, reason: str) -> None:
    """
    Recalcula balance por ledger cuando no se puede calcular delta incremental.

    Si el balance cambia, tambien emite el evento de dominio para no perder
    integraciones aguas abajo.
    """
    affected_ids = {getattr(tx, "account_id", None)}
    old_state = getattr(tx, "_old_balance_state", None)
    if old_state and old_state.account_id:
        affected_ids.add(old_state.account_id)

    fallback_context = {
        "reason": reason,
        "tx_id": str(getattr(tx, "pk", None) or ""),
        "old_state_present": old_state is not None,
        "affected_account_ids": sorted(str(account_id) for account_id in affected_ids if account_id),
    }
    logger.warning(
        "[accounts.fallback] delta_incremental_unavailable reason=%s tx_id=%s affected_accounts=%s",
        fallback_context["reason"],
        fallback_context["tx_id"],
        ",".join(fallback_context["affected_account_ids"]),
    )

    for account_id in affected_ids:
        if not account_id:
            continue

        account = Account.objects.filter(pk=account_id).first()
        if not account:
            continue

        old_balance = account.balance
        new_balance = account.recalc_balance(reason=reason)
        fallback_metadata = {
            "source": "accounts.signals.fallback_recalc",
            "reason": reason,
        }
        record_account_balance_fallback(
            account=account,
            transaction_id=getattr(tx, "pk", None),
            reason=reason,
            old_state_present=old_state is not None,
            affected_account_ids=fallback_context["affected_account_ids"],
            old_balance=old_balance,
            new_balance=new_balance,
            recalculated=bool(new_balance != old_balance),
            metadata=fallback_metadata,
        )
        if new_balance == old_balance:
            continue

        publish_account_balance_updated(
            account=account,
            old_balance=old_balance,
            new_balance=new_balance,
            reason=reason,
            transaction_id=getattr(tx, "pk", None),
            metadata=fallback_metadata,
        )

        logger.warning(
            "[accounts.fallback] recalc_applied account_id=%s tx_id=%s old=%s new=%s reason=%s",
            account_id,
            getattr(tx, "pk", None),
            old_balance,
            new_balance,
            reason,
        )
