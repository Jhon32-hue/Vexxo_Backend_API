# alerts/event_handlers.py
import logging
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from common.domain_events import (
    subscribe,
    MindwalletDomainEvent,
    EventNames,
    EventContext,
    EventPriority,
)
from finance.accounts.models.account import Account
from alerts.alerts.services import evaluate_balance_alerts_for_account  # servicio de alertas de dominio
from alerts.alerts.ai_services import enrich_alert_with_ai  # hook de IA para enriquecer alertas

logger = logging.getLogger(__name__)


# ========= HELPERS =========

def _safe_decimal(raw, fallback: str = "0") -> Decimal:
    """
    Convierte de forma segura un valor a Decimal.
    Si falla, loggea un warning y devuelve el fallback.
    """
    try:
        if raw is None or raw == "":
            raw = fallback
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning(
            "[alerts] No se pudo convertir '%s' a Decimal; usando fallback=%s",
            raw,
            fallback,
        )
        return Decimal(fallback)


# ========= LISTENER: ACCOUNT_BALANCE_UPDATED =========


@subscribe(
    EventNames.ACCOUNT_BALANCE_UPDATED,
    name="alerts.handle_account_balance_updated",
    run_async=True,  # se ejecuta en un thread aparte
    contexts=[EventContext.ACCOUNTS],  # por si en el futuro reusamos el mismo tipo en otro contexto
    priority=EventPriority.HIGH,       # que las alertas se procesen pronto
)
def handle_account_balance_updated(event: MindwalletDomainEvent) -> None:
    """
    Listener de alertas para cambios de balance en cuentas.

    Se dispara cada vez que _recalc_and_emit(...) emite el evento
    accounts.balance.updated.v1 desde accounts.signals.
    """
    payload = event.payload or {}
    correlation_id = event.correlation_id

    account_id = payload.get("account_id")
    if not account_id:
        logger.warning(
            "[alerts][corr=%s] EVENTO ACCOUNT_BALANCE_UPDATED sin account_id. payload=%s",
            correlation_id,
            payload,
        )
        return

    # Intentamos obtener la cuenta
    try:
        account = Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        logger.warning(
            "[alerts][corr=%s] Cuenta id=%s no existe; ignorando evento %s",
            correlation_id,
            account_id,
            event.type,
        )
        return

    # Si la cuenta está cerrada o archivada, podemos decidir no generar alertas
    if not getattr(account, "is_active", True) or getattr(account, "archived", False):
        logger.debug(
            "[alerts][corr=%s] Cuenta id=%s inactiva/archivada; no se evalúan alertas.",
            correlation_id,
            account_id,
        )
        return

    old_balance = _safe_decimal(payload.get("old_balance"))
    new_balance = _safe_decimal(payload.get("new_balance"))
    delta = _safe_decimal(payload.get("delta"))
    reason = payload.get("reason", "unknown")
    transaction_id = payload.get("transaction_id")

    logger.debug(
        "[alerts][corr=%s] Procesando ACCOUNT_BALANCE_UPDATED "
        "account_id=%s old=%s new=%s delta=%s reason=%s tx_id=%s",
        correlation_id,
        account_id,
        old_balance,
        new_balance,
        delta,
        reason,
        transaction_id,
    )

    # (Opcional) Umbral mínimo
    # MIN_DELTA_FOR_ALERTS = Decimal("0.00")
    # if abs(delta) < MIN_DELTA_FOR_ALERTS:
    #     logger.debug(
    #         "[alerts][corr=%s] Delta %s menor que umbral=%s; se omite evaluación.",
    #         correlation_id,
    #         delta,
    #         MIN_DELTA_FOR_ALERTS,
    #     )
    #     return

    try:
        # Llamamos al servicio de dominio que encapsula la lógica de alertas
        evaluate_balance_alerts_for_account(
            account=account,
            old_balance=old_balance,
            new_balance=new_balance,
            reason=reason,
            transaction_id=transaction_id,
            triggered_at=timezone.now(),
            correlation_id=correlation_id,
        )
        logger.debug(
            "[alerts][corr=%s] Evaluadas alertas de balance para account_id=%s",
            correlation_id,
            account_id,
        )
    except Exception:
        logger.exception(
            "[alerts][corr=%s] Error en evaluate_balance_alerts_for_account "
            "para account_id=%s",
            correlation_id,
            account_id,
        )


# ========= LISTENER: ALERT_CREATED (hook IA) =========


@subscribe(
    EventNames.ALERT_CREATED,
    name="alerts.handle_alert_created_ai",
    run_async=True,                 # que la IA no bloquee el flujo normal
    contexts=[EventContext.ALERTS],
    priority=EventPriority.LOW,     # primero se pueden procesar otras cosas críticas
)
def handle_alert_created_ai(event: MindwalletDomainEvent) -> None:
    """
    Listener que enriquece las alertas con IA cuando se crean.

    - Genera un ai_summary.
    - Puede ajustar risk_score.
    - Añade ai_tags.
    """
    payload = event.payload or {}
    correlation_id = event.correlation_id
    alert_id = payload.get("alert_id")

    if not alert_id:
        logger.debug(
            "[alerts][corr=%s] ALERT_CREATED sin alert_id en payload: %s",
            correlation_id,
            payload,
        )
        return

    from alerts.alerts.models.alerts import Alert  # import local para evitar ciclos

    try:
        alert = Alert.objects.get(pk=alert_id)
    except Alert.DoesNotExist:
        logger.warning(
            "[alerts][corr=%s] ALERT_CREATED para alert_id=%s que no existe",
            correlation_id,
            alert_id,
        )
        return

    try:
        enrich_alert_with_ai(alert, correlation_id=correlation_id)
        logger.debug(
            "[alerts][corr=%s] Alerta id=%s enriquecida con IA",
            correlation_id,
            alert_id,
        )
    except Exception:
        logger.exception(
            "[alerts][corr=%s] Error enriqueciendo alerta con IA id=%s",
            correlation_id,
            alert_id,
        )
