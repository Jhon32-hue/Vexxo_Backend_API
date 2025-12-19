from datetime import date
from decimal import Decimal
from django.db.models import Sum
from transactions.Models.transacciones import Transaction


def month_range(d: date):
    start = d.replace(day=1)
    if d.month == 12:
        end = d.replace(year=d.year + 1, month=1, day=1)
    else:
        end = d.replace(month=d.month + 1, day=1)
    return start, end


def account_month_expense_total(account, when: date) -> Decimal:
    start, end = month_range(when)
    total = Transaction.objects.filter(
        owner=account.owner,
        account=account,
        type="expense",
        date__gte=start,
        date__lt=end,
    ).aggregate(total=Sum("amount"))["total"] or 0
    return Decimal(total)


def apply_balance_effect(tx, *, old_amount=None, old_account=None):
    """
    Recalcula balances en updates:
    - si hay old_amount/old_account, revierte efecto viejo
    - aplica efecto nuevo (income suma, expense resta)
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
