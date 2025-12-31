import logging

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from accounts.models.account import Account
from transactions.Models.transacciones import Transaction  

logger = logging.getLogger(__name__)


# ========= HELPERS DE EVENTOS / ALERTAS =========

def emit_account_event(account, event_type, payload=None):
    """
    Emite un evento de dominio relacionado con una cuenta.

    La idea es conectarlo luego con el sistema de:
    - Alertas (overspending, low_balance, límites de presupuesto, etc.)
    - Notificaciones
    - Activity feed
    """
    if payload is None:
        payload = {}

    try:
        # Futuro módulo: alerts.services
        from alerts.services import publish_account_event
    except ImportError:
        # Aún no existe el módulo, no rompemos nada.
        logger.debug(
            "[events] publish_account_event no disponible. "
            "event_type=%s, account_id=%s, payload=%s",
            event_type,
            account.pk,
            payload,
        )
        return

    try:
        publish_account_event(
            account=account,
            event_type=event_type,
            payload=payload,
        )
    except Exception as e:
        logger.error(
            "[events] Error emitiendo evento de cuenta: %s",
            e,
            exc_info=True,
        )


def _recalc_and_emit(account, reason, tx=None):
    """
    Recalcula el balance de una cuenta y emite un evento de dominio si cambió.

    - reason: string corto para logging (p.ej. 'tx_created', 'tx_updated', 'tx_deleted')
    - tx: transacción relacionada (opcional, para metadata de eventos).
    """
    if account is None:
        return

    old_balance = account.balance
    new_balance = account.recalc_balance()

    if new_balance == old_balance:
        logger.debug(
            "[accounts] Balance sin cambios para '%s' (id=%s). Reason=%s",
            account.name,
            account.pk,
            reason,
        )
        return

    logger.info(
        "[accounts] 🔄 Balance actualizado para '%s' (id=%s): %s -> %s (reason=%s)",
        account.name,
        account.pk,
        old_balance,
        new_balance,
        reason,
    )

    # Emite un evento genérico de "balance actualizado"
    payload = {
        "account_id": account.pk,
        "owner_id": account.owner_id,
        "currency": account.currency,
        "old_balance": str(old_balance),
        "new_balance": str(new_balance),
        "delta": str(new_balance - old_balance),
        "reason": reason,
    }
    if tx is not None:
        payload["transaction_id"] = tx.pk
        payload["transaction_type"] = getattr(tx, "type", None)
        payload["transaction_amount"] = str(getattr(tx, "amount", None))

    emit_account_event(account, "account.balance_updated", payload)

    # Hook para el motor de alertas (presupuestos, límites, etc.)
    _check_alerts_for_account(account, old_balance, new_balance, reason, tx)


def _check_alerts_for_account(account, old_balance, new_balance, reason, tx=None):
    """
    Punto de integración con otros módulos:
    - Budgets: revisar si el usuario superó un presupuesto.
    - Alerts: disparar alertas de bajo saldo, gasto inusual, etc.
    - Reportes IA: marcar eventos relevantes para el CFO virtual.

    Implementación futura en:
    alerts.services.evaluate_balance_alerts_for_account(account, ...)
    """
    try:
        from alerts.services import evaluate_balance_alerts_for_account
    except ImportError:
        # Todavía no tienes el sistema de alertas montado, no pasa nada.
        logger.debug(
            "[alerts] evaluate_balance_alerts_for_account no disponible. "
            "account_id=%s",
            account.pk,
        )
        return

    try:
        evaluate_balance_alerts_for_account(
            account=account,
            old_balance=old_balance,
            new_balance=new_balance,
            reason=reason,
            transaction=tx,
        )
    except Exception as e:
        logger.error(
            "[alerts] Error al evaluar alertas para la cuenta id=%s: %s",
            account.pk,
            e,
            exc_info=True,
        )


# ========= SIGNALS DE Transaction =========


@receiver(pre_save, sender=Transaction)
def store_old_transaction_state(sender, instance, **kwargs):
    """
    Antes de guardar una transacción existente, guardamos el estado anterior
    relevante para poder comparar en post_save.

    Nos interesa saber:
    - account anterior
    - amount anterior
    - type/direction
    - status/confirmed (según tu modelo)

    Para nuevas transacciones (sin pk), no hay estado previo.
    """
    if not instance.pk:
        # Nueva transacción, no hay estado anterior
        instance._old_account_id = None
        instance._old_confirmed = None
        instance._old_amount = None
        instance._old_type = None
        instance._old_status = None
        return

    try:
        old = Transaction.objects.get(pk=instance.pk)
    except Transaction.DoesNotExist:
        instance._old_account_id = None
        instance._old_confirmed = None
        instance._old_amount = None
        instance._old_type = None
        instance._old_status = None
        return

    instance._old_account_id = getattr(old, "account_id", None)
    instance._old_confirmed = getattr(old, "confirmed", None)
    instance._old_amount = getattr(old, "amount", None)
    instance._old_type = getattr(old, "type", None)
    instance._old_status = getattr(old, "status", None)


@receiver(post_save, sender=Transaction)
def update_account_balance_on_transaction_save(sender, instance, created, **kwargs):
    """
    Se ejecuta cuando se crea o actualiza una transacción.

    Casos que cubre:
    - CREATE:
        * Si la transacción está confirmada, recalcula el balance de la cuenta nueva.
    - UPDATE:
        * Si cambió la cuenta A -> B, recalcula ambas.
        * Si no cambió la cuenta pero cambió amount/type/status/confirmed,
          recalcula la cuenta.
        * Si no cambió nada relevante, no hace nada.
    """
    # Detectar si la transacción debe impactar el balance (confirmed/status)
    confirmed_now = getattr(instance, "confirmed", True)  # asume True por defecto

    old_account_id = getattr(instance, "_old_account_id", None)
    confirmed_before = getattr(instance, "_old_confirmed", None)
    amount_before = getattr(instance, "_old_amount", None)
    type_before = getattr(instance, "_old_type", None)
    status_before = getattr(instance, "_old_status", None)

    new_account = instance.account
    new_account_id = new_account.pk

    # --- Caso 1: transacción nueva ---
    if created:
        if confirmed_now:
            # Nueva transacción confirmada -> impacta el balance de la cuenta nueva
            _recalc_and_emit(new_account, reason="tx_created", tx=instance)
        else:
            logger.debug(
                "[transactions] Nueva transacción no confirmada, no recalculamos balance. "
                "tx_id=%s",
                instance.pk,
            )
        return

    # --- Caso 2: transacción actualizada ---
    # Si antes no teníamos estado previo, hacemos fallback simple
    if old_account_id is None:
        # No sabemos cómo estaba antes, pero por seguridad recalc para la cuenta actual
        if confirmed_now:
            _recalc_and_emit(new_account, reason="tx_updated_no_old_state", tx=instance)
        return

    # Detectar si cambió de cuenta (A -> B)
    changed_account = old_account_id != new_account_id

    # Detectar si cambió algo relevante:
    # - amount
    # - type
    # - status/confirmed
    changed_amount = (amount_before is not None) and (amount_before != instance.amount)
    changed_type = (type_before is not None) and (type_before != getattr(instance, "type", None))
    changed_status = (status_before is not None) and (status_before != getattr(instance, "status", None))
    changed_confirmed = (
        confirmed_before is not None
        and confirmed_before != confirmed_now
    )

    something_relevant_changed = (
        changed_account
        or changed_amount
        or changed_type
        or changed_status
        or changed_confirmed
    )

    if not something_relevant_changed:
        logger.debug(
            "[transactions] Update de transacción sin cambios relevantes para balance. "
            "tx_id=%s",
            instance.pk,
        )
        return

    # Si cambió de cuenta A -> B:
    if changed_account:
        try:
            old_account = Account.objects.get(pk=old_account_id)
        except Account.DoesNotExist:
            old_account = None

        if old_account is not None:
            _recalc_and_emit(old_account, reason="tx_moved_out", tx=instance)

        if confirmed_now:
            _recalc_and_emit(new_account, reason="tx_moved_in", tx=instance)
        else:
            logger.debug(
                "[transactions] Transacción movida a otra cuenta pero no confirmada. "
                "tx_id=%s",
                instance.pk,
            )
        return

    # Si no cambió de cuenta, pero cambió amount/type/status/confirmed:
    if confirmed_now:
        _recalc_and_emit(new_account, reason="tx_updated", tx=instance)
    else:
        # Por ejemplo, confirmed pasó de True a False -> recalcular para "sacar" su efecto
        _recalc_and_emit(new_account, reason="tx_unconfirmed", tx=instance)


@receiver(post_delete, sender=Transaction)
def update_account_balance_on_transaction_delete(sender, instance, **kwargs):
    """
    Cuando se elimina una transacción, recalculamos el balance
    de la cuenta a la que pertenecía y emitimos eventos correspondientes.
    """
    account = instance.account
    if account is None:
        return

    _recalc_and_emit(account, reason="tx_deleted", tx=instance)
