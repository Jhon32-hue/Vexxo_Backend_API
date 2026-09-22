# transactions/utils_balance.py
from finance.accounts.models.account import Account


def apply_balance_effect(tx, *, old_amount=None, old_account=None):
    """
    Helper de compatibilidad.

    HISTÓRICO:
        Antes se tocaban los balances a mano desde aquí.
    AHORA:
        El balance de la cuenta se recalcula siempre desde el ledger
        (account.recalc_balance) vía señales en 'accounts.signals'.

    Este helper es seguro y NO rompe consistencia: simplemente fuerza
    un recálculo en las cuentas implicadas. Puedes usarlo desde tareas
    puntuales o scripts de mantenimiento.
    """
    if old_account is not None:
        old_account.recalc_balance()

    tx.account.recalc_balance()
