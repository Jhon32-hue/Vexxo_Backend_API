# transactions/utils_balance.py
from decimal import Decimal

def apply_balance_effect(tx, *, old_amount=None, old_account=None):
    """
    Para updates: revierte el efecto anterior y aplica el nuevo.
    """
    if old_amount is not None and old_account is not None:
        if tx.type == "expense":
            old_account.balance += Decimal(old_amount)
        else:
            old_account.balance -= Decimal(old_amount)
        old_account.save(update_fields=["balance"])

    if tx.type == "expense":
        tx.account.balance -= Decimal(tx.amount)
    else:
        tx.account.balance += Decimal(tx.amount)
    tx.account.save(update_fields=["balance"])
