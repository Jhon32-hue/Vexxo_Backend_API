# transactions/utils_limits.py
from datetime import date
from decimal import Decimal
from django.db.models import Sum
from transactions.Models.transacciones import Transaction

def _month_range(d: date):
    start = d.replace(day=1)
    if d.month == 12:
        end = d.replace(year=d.year+1, month=1, day=1)
    else:
        end = d.replace(month=d.month+1, day=1)
    return start, end

def account_month_expense_total(account, when: date) -> Decimal:
    start, end = _month_range(when)
    total = Transaction.objects.filter(
        owner=account.owner, account=account, type="expense",
        date__gte=start, date__lt=end
    ).aggregate(total=Sum("amount"))["total"] or 0
    return Decimal(total)
