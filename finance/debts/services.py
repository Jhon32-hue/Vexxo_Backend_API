from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction

from finance.debts.models import Debt, DebtInstallment
from finance.debts.utils import add_months, add_weeks, q


@transaction.atomic
def generate_installments_for_debt(debt: Debt) -> int:
    """
    Genera las cuotas de una deuda de forma idempotente.

    - Calcula interés simple o fijo por cuota.
    - Soporta frecuencia mensual, quincenal o semanal.
    - Evita duplicados (idempotente).
    - Ajusta redondeos en la última cuota.
    """

    n = debt.total_installments or 0
    if n <= 0:
        return 0

    # Evita doble generación
    if DebtInstallment.objects.filter(debt=debt).exists():
        return 0

    principal = q(debt.principal)
    rate = q(debt.interest_rate or 0)
    per_inst_principal = (principal / q(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    remaining = principal
    created = 0

    for i in range(1, n + 1):
        # Cálculo del interés
        interest = Decimal("0.00")
        if debt.interest_type != "none":
            interest = (remaining * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Ajuste de la última cuota por residuo
        principal_component = per_inst_principal if i < n else remaining
        amount_due = (principal_component + interest).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Fecha según frecuencia
        due_date = debt.start_date
        if debt.frequency == "monthly":
            due_date = add_months(debt.start_date, i - 1)
        elif debt.frequency == "biweekly":
            due_date = add_weeks(debt.start_date, (i - 1) * 2)
        elif debt.frequency == "weekly":
            due_date = add_weeks(debt.start_date, i - 1)

        DebtInstallment.objects.create(
            owner=debt.owner,
            debt=debt,
            number=i,
            due_date=due_date,
            amount_due=amount_due,
            principal_component=principal_component,
            interest_component=interest,
        )

        remaining = (remaining - principal_component).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        created += 1

    # Actualiza saldo inicial de deuda
    debt.status = "active"
    debt.save(update_fields=["status"])

    return created


@transaction.atomic
def apply_payment_to_debt(
    debt: Debt,
    amount: Decimal,
    pay_date: date,
    installment: Optional[DebtInstallment] = None,
) -> None:
    """
    Aplica un pago a una deuda (o una cuota específica).

    - Distribuye el pago sobre las cuotas pendientes.
    - Marca cuotas como 'partial' o 'paid'.
    - Cierra la deuda si todas las cuotas quedan pagadas.
    """

    amt = q(amount)
    if amt <= 0:
        return

    installments_qs = DebtInstallment.objects.filter(debt=debt).order_by("number")
    if installment is not None:
        installments_qs = installments_qs.filter(pk=installment.pk)

    for inst in installments_qs.select_for_update():
        if amt <= 0:
            break
        outstanding = q(inst.amount_due - inst.paid_amount)
        if outstanding <= 0:
            continue

        pay = min(outstanding, amt)
        inst.paid_amount = (inst.paid_amount + pay).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        inst.paid_date = pay_date
        inst.status = "paid" if inst.paid_amount >= inst.amount_due else "partial"
        inst.save(update_fields=["paid_amount", "paid_date", "status"])

        amt -= pay

    # Actualiza estado de deuda
    if not DebtInstallment.objects.filter(debt=debt).exclude(status="paid").exists():
        debt.status = "closed"
    elif DebtInstallment.objects.filter(debt=debt, status="overdue").exists():
        debt.status = "overdue"
    else:
        debt.status = "active"
    debt.save(update_fields=["status"])
