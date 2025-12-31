# transactions/signals.py

import logging
from decimal import Decimal

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from transactions.Models.transacciones import Transaction, ScheduledPayment
from transactions.utils_limits import account_month_expense_total

logger = logging.getLogger(__name__)


def _apply_debt_payment_if_any(instance: Transaction):
    """
    Si la transacción está asociada a una deuda/cuota y es de tipo 'expense',
    delegamos el manejo a debts.services.apply_payment_to_debt (si existe).
    """
    if instance.type != "expense" or not instance.debt_id:
        return

    try:
        from debts.services import apply_payment_to_debt
    except ImportError:
        logger.debug(
            "[transactions] debts.services.apply_payment_to_debt no disponible."
        )
        return

    try:
        installment = instance.installment if instance.installment_id else None
        apply_payment_to_debt(
            debt=instance.debt,
            amount=Decimal(instance.amount),
            pay_date=instance.date,
            installment=installment,
            transaction=instance,
        )
        logger.info(
            "[transactions] Pago aplicado a deuda id=%s via tx id=%s",
            instance.debt_id,
            instance.pk,
        )
    except Exception as e:
        logger.error(
            "[transactions] Error aplicando pago a deuda para tx id=%s: %s",
            instance.pk,
            e,
            exc_info=True,
        )


def _mark_scheduled_payment_as_paid(instance: Transaction):
    """
    Si la transacción está vinculada a un ScheduledPayment, lo marcamos como 'paid'
    (si aún no lo está).
    """
    if not instance.scheduled_payment_id:
        return

    sp = ScheduledPayment.objects.filter(pk=instance.scheduled_payment_id).first()
    if not sp or sp.status == ScheduledPayment.Status.PAID:
        return

    sp.status = ScheduledPayment.Status.PAID
    sp.save(update_fields=["status"])
    logger.info(
        "[transactions] Pago programado '%s' marcado como paid via tx id=%s",
        sp.name,
        instance.pk,
    )


def _raise_monthly_limit_alert_if_needed(instance: Transaction):
    """
    Si la cuenta tiene límite mensual y NO está en modo 'lock_on_limit',
    generamos alerta cuando el total del mes excede el límite.
    """
    if instance.type != "expense":
        return

    account = instance.account
    monthly_limit = getattr(account, "monthly_expense_limit", None)
    lock_on_limit = getattr(account, "lock_on_limit", False)

    if not monthly_limit or lock_on_limit:
        return

    month_total = account_month_expense_total(account, instance.date)

    if Decimal(month_total) <= Decimal(monthly_limit):
        return

    payload = {
        "account_id": account.pk,
        "account_name": account.name,
        "month_total": float(month_total),
        "limit": float(monthly_limit),
        "currency": account.currency,
        "message": (
            f"Has superado el límite mensual de gastos para la cuenta {account.name}."
        ),
        "transaction_id": instance.pk,
        "date": instance.date.isoformat(),
    }

    try:
        from alerts.models import Alert
    except ImportError:
        logger.debug(
            "[transactions] alerts.models.Alert no disponible. Payload=%s",
            payload,
        )
        return

    try:
        Alert.objects.create(
            owner=instance.owner,
            type="over_spend",
            payload=payload,
        )
        logger.info(
            "[transactions] Alert over_spend creada para account_id=%s",
            account.pk,
        )
    except Exception as e:
        logger.error(
            "[transactions] Error creando alerta over_spend: %s",
            e,
            exc_info=True,
        )


@receiver(post_save, sender=Transaction)
def on_transaction_post_save(sender, instance: Transaction, created: bool, **kwargs):
    """
    Side effects de transacciones:
    - marcan pagos programados como pagados
    - aplican pagos a deudas/cuotas
    - generan alertas por límite mensual

    El cálculo de balances de Account se maneja en accounts.signals,
    usando account.recalc_balance().
    """
    try:
        _mark_scheduled_payment_as_paid(instance)
        _apply_debt_payment_if_any(instance)
        _raise_monthly_limit_alert_if_needed(instance)
    except Exception as e:
        logger.error(
            "[transactions] Error en on_transaction_post_save para tx id=%s: %s",
            instance.pk,
            e,
            exc_info=True,
        )


@receiver(post_delete, sender=Transaction)
def on_transaction_post_delete(sender, instance: Transaction, **kwargs):
    """
    De momento solo registramos el borrado.
    El rebalanceo de cuentas lo maneja accounts.signals.

    Futuro: podrías ajustar deudas/cuotas cuando se borra un pago
    (reverso de pagamento), si lo necesitas.
    """
    logger.info(
        "[transactions] Transacción eliminada id=%s type=%s amount=%s",
        instance.pk,
        instance.type,
        instance.amount,
    )
