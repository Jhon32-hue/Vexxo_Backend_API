# transactions/signals.py

import logging
from decimal import Decimal

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum, Q
from django.utils import timezone

from finance.transactions.Models.transacciones import Transaction, ScheduledPayment
from finance.transactions.Models.transacciones import TransactionParticipant
from contacts.models.contact import Contact
from finance.transactions.utils_limits import account_month_expense_total
from identity.users.services.product_usage_projection_service import (
    sync_scheduled_payments_slice,
)

logger = logging.getLogger(__name__)


# ================== HELPERS EXISTENTES ==================


def _apply_debt_payment_if_any(instance: Transaction):
    """
    Si la transacción está asociada a una deuda/cuota y es de tipo 'expense',
    delegamos el manejo a debts.services.apply_payment_to_debt (si existe).
    """
    if instance.type != "expense" or not instance.debt_id:
        return

    try:
        from finance.debts.services import apply_payment_to_debt
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
        from alerts.alerts.models import Alert
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


# ================== NUEVO: CONTACTOS / PARTICIPANTES ==================


def _recalc_contact_balance_from_participants(contact: Contact):
    """
    Recalcula el saldo neto con un contacto a partir de TODAS las
    participaciones activas (TransactionParticipant).

    net > 0  => el contacto ME debe
    net < 0  => YO le debo
    net == 0 => liquidado

    Si el modelo Contact ya tiene un método recalc_net_balance(), se usa.
    Si no, calculamos aquí y, si existen campos apropiados, los actualizamos.
    """
    # Si el modelo ya implementa su propia lógica, la usamos
    if hasattr(contact, "recalc_net_balance") and callable(contact.recalc_net_balance):
        try:
            return contact.recalc_net_balance()
        except Exception as e:
            logger.error(
                "[transactions] Error llamando contact.recalc_net_balance "
                "para contact_id=%s: %s",
                contact.pk,
                e,
                exc_info=True,
            )

    # Fallback: cálculo directo desde TransactionParticipant
    qs = TransactionParticipant.objects.filter(
        contact=contact,
        status=TransactionParticipant.Status.ACTIVE,
    )

    agg = qs.aggregate(
        total_creditor=Sum(
            "share_amount",
            filter=Q(
                direction=TransactionParticipant.Direction.USER_IS_CREDITOR
            ),
        ),
        total_debtor=Sum(
            "share_amount",
            filter=Q(
                direction=TransactionParticipant.Direction.USER_IS_DEBTOR
            ),
        ),
    )

    total_creditor = agg["total_creditor"] or 0
    total_debtor = agg["total_debtor"] or 0
    net = Decimal(total_creditor) - Decimal(total_debtor)

    fields_to_update = []

    # Campos opcionales en Contact (si los tienes)
    if hasattr(contact, "balance_net"):
        contact.balance_net = net
        fields_to_update.append("balance_net")

    if hasattr(contact, "balance_they_owe_me"):
        contact.balance_they_owe_me = max(Decimal("0.00"), net)
        fields_to_update.append("balance_they_owe_me")

    if hasattr(contact, "balance_i_owe"):
        contact.balance_i_owe = max(Decimal("0.00"), -net)
        fields_to_update.append("balance_i_owe")

    if hasattr(contact, "last_activity_at"):
        contact.last_activity_at = timezone.now()
        fields_to_update.append("last_activity_at")

    if fields_to_update:
        contact.save(update_fields=fields_to_update)

    return net


def _recalc_contact_balances_for_tx(instance: Transaction):
    """
    Recalcula el net_balance de todos los contactos involucrados en una transacción.
    """
    participants = (
        TransactionParticipant.objects.filter(
            transaction=instance, contact__isnull=False
        )
        .select_related("contact")
        .all()
    )

    touched = set()
    for part in participants:
        contact = part.contact
        if contact and contact.pk not in touched:
            touched.add(contact.pk)
            try:
                _recalc_contact_balance_from_participants(contact)
                logger.debug(
                    "[transactions] net_balance recalculado para contact_id=%s",
                    contact.pk,
                )
            except Exception as e:
                logger.error(
                    "[transactions] Error recalculando net_balance para contact_id=%s: %s",
                    contact.pk,
                    e,
                    exc_info=True,
                )


def _sync_scheduled_payment_usage(owner_id, *, source: str):
    if not owner_id:
        return
    try:
        sync_scheduled_payments_slice(owner_id, source=source)
    except Exception as e:
        logger.error(
            "[transactions] Error sincronizando scheduled payment usage owner_id=%s: %s",
            owner_id,
            e,
            exc_info=True,
        )


# ================== SIGNALS SOBRE TRANSACTION ==================


@receiver(post_save, sender=Transaction)
def on_transaction_post_save(sender, instance: Transaction, created: bool, **kwargs):
    """
    Side effects de transacciones:
    - marcan pagos programados como pagados
    - aplican pagos a deudas/cuotas
    - generan alertas por límite mensual
    - recalculan saldo neto de contactos involucrados

    El cálculo de balances de Account se maneja en accounts.signals,
    usando account.recalc_balance().
    """
    try:
        _mark_scheduled_payment_as_paid(instance)
        _apply_debt_payment_if_any(instance)
        _raise_monthly_limit_alert_if_needed(instance)
        _recalc_contact_balances_for_tx(instance)
        if instance.scheduled_payment_id:
            _sync_scheduled_payment_usage(
                instance.owner_id,
                source="finance.transactions.signals.on_transaction_post_save.scheduled_payment",
            )
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
    Registramos el borrado y recalculamos los contactos involucrados.
    El rebalanceo de cuentas lo maneja accounts.signals.

    Futuro: podrías ajustar deudas/cuotas cuando se borra un pago
    (reverso de pago), si lo necesitas.
    """
    logger.info(
        "[transactions] Transacción eliminada id=%s type=%s amount=%s",
        instance.pk,
        instance.type,
        instance.amount,
    )
    try:
        _recalc_contact_balances_for_tx(instance)
        if instance.scheduled_payment_id:
            _sync_scheduled_payment_usage(
                instance.owner_id,
                source="finance.transactions.signals.on_transaction_post_delete.scheduled_payment",
            )
    except Exception as e:
        logger.error(
            "[transactions] Error recalculando net_balance tras delete tx id=%s: %s",
            instance.pk,
            e,
            exc_info=True,
        )


# ================== SIGNALS SOBRE TransactionParticipant ==================


@receiver(post_save, sender=TransactionParticipant)
def on_participant_post_save(
    sender, instance: TransactionParticipant, created, **kwargs
):
    """
    Cada vez que se crea/actualiza un participante, recalculamos el saldo del contacto.
    """
    try:
        if instance.contact_id:
            _recalc_contact_balance_from_participants(instance.contact)
    except Exception as e:
        logger.error(
            "[transactions] Error en on_participant_post_save contact_id=%s: %s",
            getattr(instance.contact, "pk", None),
            e,
            exc_info=True,
        )


@receiver(post_delete, sender=TransactionParticipant)
def on_participant_post_delete(sender, instance: TransactionParticipant, **kwargs):
    """
    Cuando se elimina un participante, también recalculamos el saldo del contacto.
    """
    try:
        if instance.contact_id:
            contact = Contact.objects.filter(pk=instance.contact_id).first()
            if contact:
                _recalc_contact_balance_from_participants(contact)
    except Exception as e:
        logger.error(
            "[transactions] Error en on_participant_post_delete contact_id=%s: %s",
            getattr(instance.contact, "pk", None),
            e,
            exc_info=True,
        )


@receiver(post_save, sender=ScheduledPayment)
def on_scheduled_payment_post_save(sender, instance: ScheduledPayment, **kwargs):
    _sync_scheduled_payment_usage(
        instance.owner_id,
        source="finance.transactions.signals.on_scheduled_payment_post_save",
    )


@receiver(post_delete, sender=ScheduledPayment)
def on_scheduled_payment_post_delete(sender, instance: ScheduledPayment, **kwargs):
    _sync_scheduled_payment_usage(
        instance.owner_id,
        source="finance.transactions.signals.on_scheduled_payment_post_delete",
    )
