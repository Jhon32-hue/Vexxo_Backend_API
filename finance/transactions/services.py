from datetime import date
from decimal import Decimal

from django.db.models import Sum

from finance.transactions.Models.transacciones import Transaction
from .utils_limits import month_range, account_month_expense_total
from finance.transactions.transaction_state_service import LEDGER_COUNTABLE_STATUSES


__all__ = [
    "month_range",
    "account_month_expense_total",
    "user_monthly_expense_total",
    "user_category_expense_summary",
]


def user_monthly_expense_total(user, when: date) -> Decimal:
    """
    Total de gastos de TODO el usuario en el mes de 'when'
    (todas las cuentas, solo transacciones contabilizadas).
    """
    start, end = month_range(when)
    total = (
        Transaction.objects.filter(
            owner=user,
            type=Transaction.Type.EXPENSE,
            status__in=LEDGER_COUNTABLE_STATUSES,
            confirmed=True,
            date__gte=start,
            date__lt=end,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    return Decimal(total)


def user_category_expense_summary(user, when: date):
    """
    Resumen de gastos por categoría en el mes de 'when'.
    Solo transacciones contabilizadas.
    """
    start, end = month_range(when)
    qs = (
        Transaction.objects.filter(
            owner=user,
            type=Transaction.Type.EXPENSE,
            status__in=LEDGER_COUNTABLE_STATUSES,
            confirmed=True,
            date__gte=start,
            date__lt=end,
            category__isnull=False,
        )
        .values("category_id", "category__name")
        .annotate(total_amount=Sum("amount"))
        .order_by("-total_amount")
    )
    return qs
