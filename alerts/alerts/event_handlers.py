# alerts/event_handlers.py
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from common.domain_events import (
    subscribe,
    VexxoAppDomainEvent,
    EventNames,
    EventContext,
    EventPriority,
)
from finance.accounts.models.account import Account
from alerts.alerts.models.alerts import Alert, AlertCategory, AlertSeverity, AlertType
from alerts.alerts.services import create_alert, evaluate_balance_alerts_for_account  # servicio de alertas de dominio
from alerts.alerts.dispatch_service import dispatch_alert_ai_enrichment

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


def _has_recent_system_alert(*, owner_id, source: str, account_id, minutes: int = 60) -> bool:
    since = timezone.now() - timedelta(minutes=minutes)
    return Alert.objects.filter(
        owner_id=owner_id,
        type=AlertType.SYSTEM,
        source=source,
        is_active=True,
        created_at__gte=since,
        payload__account_id=account_id,
    ).exists()


# ========= LISTENER: ACCOUNT_BALANCE_UPDATED =========


@subscribe(
    EventNames.ACCOUNT_BALANCE_UPDATED,
    name="alerts.handle_account_balance_updated",
    run_async=True,  # se ejecuta en un thread aparte
    contexts=[EventContext.ACCOUNTS],  # por si en el futuro reusamos el mismo tipo en otro contexto
    priority=EventPriority.HIGH,       # que las alertas se procesen pronto
)
def handle_account_balance_updated(event: VexxoAppDomainEvent) -> None:
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
    run_async=False,
    contexts=[EventContext.ALERTS],
    priority=EventPriority.LOW,     # primero se pueden procesar otras cosas críticas
)
def handle_alert_created_ai(event: VexxoAppDomainEvent) -> None:
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

    try:
        dispatch_result = dispatch_alert_ai_enrichment(
            alert_id=alert_id,
            correlation_id=correlation_id or "",
            source="alerts.event_handlers.handle_alert_created_ai",
        )
        logger.debug(
            "[alerts][corr=%s] Enriquecimiento IA despachado alert_id=%s result=%s",
            correlation_id,
            alert_id,
            dispatch_result.get("result"),
        )
    except Exception:
        logger.exception(
            "[alerts][corr=%s] Error despachando enriquecimiento IA id=%s",
            correlation_id,
            alert_id,
        )


@subscribe(
    EventNames.ACCOUNT_SYNC_FAILED,
    name="alerts.handle_account_sync_failed",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.HIGH,
)
def handle_account_sync_failed(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    account_id = payload.get("account_id")
    correlation_id = event.correlation_id
    if not account_id:
        return

    try:
        account = Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        logger.warning(
            "[alerts][corr=%s] ACCOUNT_SYNC_FAILED para cuenta inexistente id=%s",
            correlation_id,
            account_id,
        )
        return

    try:
        if _has_recent_system_alert(
            owner_id=account.owner_id,
            source="alerts.event_handlers.handle_account_sync_failed",
            account_id=account.pk,
        ):
            return
        create_alert(
            owner=account.owner,
            type=AlertType.SYSTEM,
            title=f"Error de sincronizacion en {account.name}",
            message=(
                f"La sincronizacion de la cuenta {account.name} con el proveedor "
                f"{payload.get('provider') or account.provider or 'externo'} fallo. "
                f"Motivo: {payload.get('message') or 'sin detalle'}."
            ),
            category=AlertCategory.SYSTEM,
            severity=AlertSeverity.WARNING,
            payload={
                "account_id": account.pk,
                "provider": payload.get("provider") or account.provider,
                "sync_status": payload.get("sync_status") or account.sync_status,
                "next_sync_at": payload.get("next_sync_at"),
                "event_type": event.type,
            },
            source="alerts.event_handlers.handle_account_sync_failed",
            correlation_id=correlation_id,
        )
    except Exception:
        logger.exception(
            "[alerts][corr=%s] Error generando alerta para ACCOUNT_SYNC_FAILED account_id=%s",
            correlation_id,
            account_id,
        )


@subscribe(
    EventNames.ACCOUNT_DRIFT_DETECTED,
    name="alerts.handle_account_drift_detected",
    run_async=True,
    contexts=[EventContext.ACCOUNTS],
    priority=EventPriority.HIGH,
)
def handle_account_drift_detected(event: VexxoAppDomainEvent) -> None:
    payload = event.payload or {}
    account_id = payload.get("account_id")
    correlation_id = event.correlation_id
    if not account_id:
        return

    try:
        account = Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        logger.warning(
            "[alerts][corr=%s] ACCOUNT_DRIFT_DETECTED para cuenta inexistente id=%s",
            correlation_id,
            account_id,
        )
        return

    try:
        if _has_recent_system_alert(
            owner_id=account.owner_id,
            source="alerts.event_handlers.handle_account_drift_detected",
            account_id=account.pk,
        ):
            return
        create_alert(
            owner=account.owner,
            type=AlertType.SYSTEM,
            title=f"Inconsistencia de balance detectada en {account.name}",
            message=(
                f"Se detecto drift entre el balance cacheado y el ledger de la cuenta "
                f"{account.name}. Drift absoluto: {payload.get('drift_abs')} {account.currency}."
            ),
            category=AlertCategory.SYSTEM,
            severity=AlertSeverity.CRITICAL,
            payload={
                "account_id": account.pk,
                "snapshot_id": payload.get("snapshot_id"),
                "drift": payload.get("drift"),
                "drift_abs": payload.get("drift_abs"),
                "drift_threshold": payload.get("drift_threshold"),
                "source": payload.get("source"),
                "event_type": event.type,
            },
            source="alerts.event_handlers.handle_account_drift_detected",
            correlation_id=correlation_id,
        )
    except Exception:
        logger.exception(
            "[alerts][corr=%s] Error generando alerta para ACCOUNT_DRIFT_DETECTED account_id=%s",
            correlation_id,
            account_id,
        )
