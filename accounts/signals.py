import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from accounts.models import Account
from transactions.Models.transacciones import Transaction

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=Transaction)
def update_account_balance_on_transaction_change(sender, instance, **kwargs):
    """
    Cada vez que se crea, modifica o elimina una transacción,
    actualiza el balance de la cuenta correspondiente.
    """
    try:
        account = instance.account
        new_balance = account.recalc_balance()
        logger.info(f"[accounts] 🔄 Balance actualizado para '{account.name}': {new_balance}")
    except Exception as e:
        logger.error(f"[accounts] ⚠️ Error recalculando balance: {e}")
