from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from calendar import monthrange


def add_months(d: date, months: int) -> date:
    """Suma meses (corrige límites de mes)."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def add_weeks(d: date, weeks: int) -> date:
    """Suma semanas, útil para deudas semanales/quincenales."""
    return d + timedelta(weeks=weeks)


def q(x) -> Decimal:
    """Convierte a Decimal con precisión de 2 decimales."""
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
