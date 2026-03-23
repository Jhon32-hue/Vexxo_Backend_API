# accounts/signals.py
import logging
from django.apps import apps
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from finance.accounts.domain.enums import BalanceChangeReason
from finance.accounts.models.account import Account
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
    """
    affected_ids = {getattr(tx, "account_id", None)}
    old_state = getattr(tx, "_old_balance_state", None)
    if old_state and old_state.account_id:
        affected_ids.add(old_state.account_id)

    for account_id in affected_ids:
        if not account_id:
            continue

        account = Account.objects.filter(pk=account_id).first()
        if not account:
            continue

        old_balance = account.balance
        new_balance = account.recalc_balance()
        if new_balance == old_balance:
            continue

        logger.warning(
            "[accounts] Fallback recalc account_id=%s tx_id=%s old=%s new=%s reason=%s",
            account_id,
            getattr(tx, "pk", None),
            old_balance,
            new_balance,
            reason,
        )
