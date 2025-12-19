# transactions/signals.py  (reemplaza el tuyo; incluye TU lógica + extras)

import logging
from decimal import Decimal
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from transactions.Models.transacciones import Transaction, ScheduledPayment
from debts.services import apply_payment_to_debt

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Transaction)
def on_tx_create(sender, instance: Transaction, created: bool, **kwargs):
    if not created:
        return
    try:
        # 0) actualizar balance de la cuenta
        acc = instance.account
        if instance.type == "expense":
            acc.balance -= Decimal(instance.amount)
        elif instance.type == "income":
            acc.balance += Decimal(instance.amount)
        acc.save(update_fields=["balance"])

        # 1) scheduled payment -> paid (tu lógica)
        if instance.scheduled_payment_id:
            sp = ScheduledPayment.objects.filter(pk=instance.scheduled_payment_id).first()
            if sp and sp.status != "paid":
                sp.status = "paid"
                sp.save(update_fields=["status"])
                logger.info(f"[transactions] Pago programado '{sp.name}' => paid")

        # 2) aplicar pago a deuda/cuota (tu lógica)
        if instance.type == "expense" and instance.debt_id:
            installment = instance.installment if instance.installment_id else None
            apply_payment_to_debt(
                debt=instance.debt,
                amount=Decimal(instance.amount),
                pay_date=instance.date,
                installment=installment,
            )

        # 3) alerta por límite mensual de la cuenta (si existe y no está lock)
        #    esto no bloquea, solo alerta. El bloqueo lo hace el serializer.
        acc.refresh_from_db(fields=["monthly_expense_limit", "lock_on_limit"])
        if instance.type == "expense" and getattr(acc, "monthly_expense_limit", None) and not getattr(acc, "lock_on_limit", False):
            from transactions.utils_limits import account_month_expense_total
            total_mes = account_month_expense_total(acc, instance.date)
            if Decimal(total_mes) > Decimal(acc.monthly_expense_limit):
                try:
                    from alerts.models import Alert
                    Alert.objects.create(
                        owner=instance.owner,
                        type="over_spend",
                        payload={
                            "account": acc.name,
                            "month_total": float(total_mes),
                            "limit": float(acc.monthly_expense_limit),
                            "message": f"Has superado el límite mensual de {acc.name}.",
                        },
                    )
                except Exception:  # si no tienes alerts aún, ignora
                    pass

    except Exception as e:
        logger.error(f"[transactions] Error en post_save: {e}", exc_info=True)

@receiver(post_delete, sender=Transaction)
def on_tx_delete(sender, instance: Transaction, **kwargs):
    """Reversa el efecto en el balance al eliminar la transacción."""
    try:
        acc = instance.account
        if instance.type == "expense":
            acc.balance += Decimal(instance.amount)
        elif instance.type == "income":
            acc.balance -= Decimal(instance.amount)
        acc.save(update_fields=["balance"])
    except Exception as e:
        logger.error(f"[transactions] Error en post_delete: {e}", exc_info=True)
