from datetime import date
from decimal import Decimal

from django.db.models import Sum

from finance.transactions.Models.transacciones import Transaction


def month_range(d: date):
    """
    Devuelve (inicio, fin_exclusivo) del mes de la fecha dada.
    Ej: 2025-02-15 -> (2025-02-01, 2025-03-01)
    """
    start = d.replace(day=1)
    if d.month == 12:
        end = d.replace(year=d.year + 1, month=1, day=1)
    else:
        end = d.replace(month=d.month + 1, day=1)
    return start, end


def account_month_expense_total(account, when: date) -> Decimal:
    """
    Total de gastos (expense) de UNA cuenta en el mes de 'when'.
    Solo transacciones contabilizadas (posted/reconciled) y confirmadas.
    """
    start, end = month_range(when)
    total = (
        Transaction.objects.filter(
            owner=account.owner,
            account=account,
            type=Transaction.Type.EXPENSE,
            status__in=[Transaction.Status.POSTED, Transaction.Status.RECONCILED],
            confirmed=True,
            date__gte=start,
            date__lt=end,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    return Decimal(total)


def user_month_tx_count(user, when: date) -> int:
    """
    Número de transacciones del usuario en el mes de 'when'.
    Se usa para límites de transacciones por plan (free/plus/pro).
    Cuenta todas, independientemente del estado.
    """
    start, end = month_range(when)
    return Transaction.objects.filter(
        owner=user,
        date__gte=start,
        date__lt=end,
    ).count()
