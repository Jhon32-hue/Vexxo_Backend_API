import logging
from datetime import date

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from finance.debts.models import Debt, DebtInstallment
from finance.debts.services import generate_installments_for_debt, apply_payment_to_debt
from finance.transactions.Models.transacciones import Transaction

logger = logging.getLogger(__name__)


# ============================================================
# 1️⃣ Generar cuotas automáticamente cuando se crea una deuda
# ============================================================

@receiver(post_save, sender=Debt)
def debt_post_save(sender, instance: Debt, created: bool, **kwargs):
    """
    Cuando se crea una deuda nueva, genera automáticamente las cuotas
    según sus parámetros (número de cuotas, frecuencia, tasa, etc.)
    """
    if not created:
        return

    try:
        count = generate_installments_for_debt(instance)
        if count > 0:
            logger.info(f"[debts] ✅ Generadas {count} cuotas para deuda '{instance.name}' (ID {instance.id})")
        else:
            logger.warning(f"[debts] ⚠️ No se generaron cuotas para '{instance.name}' — puede que ya existan.")
    except Exception as e:
        logger.error(f"[debts] ❌ Error generando cuotas para '{instance.name}': {e}")


# ============================================================
# 2️⃣ Actualizar estado de la deuda cuando cambia una cuota
# ============================================================

@receiver(post_save, sender=DebtInstallment)
def update_debt_status_on_installment_save(sender, instance: DebtInstallment, **kwargs):
    """
    Cada vez que se crea o actualiza una cuota, se recalcula el estado
    general de la deuda (active | closed | overdue).
    """
    debt = instance.debt
    installments = debt.installments.all()

    all_paid = all(i.status == "paid" for i in installments)
    any_overdue = any(i.status == "overdue" for i in installments)

    new_status = "active"
    if all_paid:
        new_status = "closed"
    elif any_overdue:
        new_status = "overdue"

    if debt.status != new_status:
        debt.status = new_status
        debt.save(update_fields=["status"])
        logger.info(f"[debts] 🔄 Estado de deuda '{debt.name}' actualizado a '{new_status}'.")


# ============================================================
# 3️⃣ Marcar automáticamente las cuotas vencidas
# ============================================================

@receiver(post_save, sender=DebtInstallment)
def mark_overdue_installments(sender, instance: DebtInstallment, **kwargs):
    """
    Si una cuota aún está pendiente y la fecha de vencimiento pasó,
    se marca como 'overdue' automáticamente.
    """
    today = date.today()
    if instance.status == "due" and instance.due_date < today:
        instance.status = "overdue"
        instance.save(update_fields=["status"])
        logger.info(f"[debts] ⏰ Cuota #{instance.number} de '{instance.debt.name}' marcada como VENCIDA.")


# ============================================================
# 4️⃣ Recalcular estado de la deuda si se elimina una cuota
# ============================================================

@receiver(post_delete, sender=DebtInstallment)
def update_debt_status_on_installment_delete(sender, instance: DebtInstallment, **kwargs):
    """
    Si se elimina una cuota (por ejemplo, ajuste manual), se recalcula
    el estado de la deuda asociada.
    """
    debt = instance.debt
    remaining = debt.installments.all()

    if not remaining.exists():
        debt.status = "active"
        debt.save(update_fields=["status"])
        logger.warning(f"[debts] ⚠️ Todas las cuotas de '{debt.name}' fueron eliminadas. Estado: ACTIVE.")
        return

    all_paid = all(i.status == "paid" for i in remaining)
    any_overdue = any(i.status == "overdue" for i in remaining)

    new_status = "active"
    if all_paid:
        new_status = "closed"
    elif any_overdue:
        new_status = "overdue"

    if debt.status != new_status:
        debt.status = new_status
        debt.save(update_fields=["status"])
        logger.info(f"[debts] ♻️ Estado de deuda '{debt.name}' recalculado tras eliminar una cuota: {new_status}.")


# ============================================================
# 5️⃣ (Opcional) Aplicar pago automáticamente desde transacción
# ============================================================

# ⚠️ Esta señal se activa si una transacción referencia una deuda
# o una cuota específica. Esto cierra el circuito entre ambos módulos.

try:
    from finance.transactions.Models.transacciones import Transaction
except Exception:
    Transaction = None

if Transaction:
    @receiver(post_save, sender=Transaction)
    def auto_apply_debt_payment(sender, instance, created, **kwargs):
        """
        Cuando se registra una transacción con una deuda o cuota asociada,
        aplica el monto automáticamente a la deuda.
        """
        if not created or not instance.debt:
            return

        try:
            apply_payment_to_debt(
                debt=instance.debt,
                amount=instance.amount,
                pay_date=instance.date,
                installment=instance.installment,
            )
            logger.info(f"[debts] 💰 Pago automático aplicado a deuda '{instance.debt.name}' (Transacción #{instance.id}).")
        except Exception as e:
            logger.error(f"[debts] ❌ Error aplicando pago automático a deuda '{instance.debt.name}': {e}")
