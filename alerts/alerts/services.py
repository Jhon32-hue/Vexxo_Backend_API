# alerts/services.py
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.utils import timezone

from alerts.alerts.models.alerts import (
    Alert,
    AlertType,
    AlertCategory,
    AlertSeverity,
    AlertStatus,
)
from common.domain_events import (
    EventContext,
    EventNames,
    EventPriority,
)
from alerts.alerts.event_service import publish_alert_event_after_commit

logger = logging.getLogger(__name__)


# ========= FACTORÍA CENTRAL DE ALERTAS =========


def create_alert(
    *,
    owner,
    type: str,
    title: str,
    message: str,
    category: str = AlertCategory.SPENDING,
    severity: str = AlertSeverity.INFO,
    payload: Optional[Dict[str, Any]] = None,
    source: str = "alerts.services",
    correlation_id: Optional[str] = None,
    risk_score: Optional[Decimal] = None,
) -> Alert:
    """
    Punto único para crear alertas en Vexxo_app.

    Flujo actual:
      1) Crea la alerta en DB con un estado inicial (NEW / activa).
      2) Publica evento de dominio ALERT_CREATED en el Event Bus.
      3) Intenta enriquecer la alerta con IA (ai_summary, risk_score, ai_tags)
         usando alerts.ai_services.enrich_alert_with_ai, que a su vez
         publicará ALERT_AI_ENRICHED.

    Ventajas:
      - Cualquier módulo que use create_alert obtiene:
          * Persistencia consistente.
          * Eventos de dominio (para dashboards, notificaciones, etc.).
          * Enriquecimiento opcional por IA, sin acoplarse a detalles de LLM.
      - Para tests, se puede mockear este servicio y no tocar el resto del sistema.

    Ejemplos de uso:
      - Desde reglas de gasto: evaluate_balance_alerts_for_account(...)
      - Desde pagos programados: generate_scheduled_payment_alerts(...)
      - Desde otros módulos (debts, goals, budgets, fx, etc.):

          create_alert(
              owner=user,
              type=AlertType.LOW_BALANCE,
              title="Saldo bajo en tu cuenta",
              message="Tu saldo de Nequi está por debajo de 50.000 COP...",
              category=AlertCategory.CASHFLOW,
              severity=AlertSeverity.WARNING,
              payload={...},
              source="debts.services.check_low_balance",
              correlation_id=some_correlation_id,
          )
    """
    payload = payload or {}

    alert = Alert.objects.create(
        owner=owner,
        type=type,
        category=category,
        severity=severity,
        status=AlertStatus.NEW,
        title=title,
        message=message,
        payload=payload,
        source=source,
        correlation_id=correlation_id or "",
        risk_score=risk_score,
        is_active=True,
    )

    # 1) Evento de dominio: alerts.created.v1
    #    Otros módulos pueden escuchar esto para:
    #      - Contar alertas nuevas.
    #      - Actualizar un "inbox" o feed de notificaciones.
    #      - Disparar integraciones externas (webhooks, etc.).
    publish_alert_event_after_commit(
        event_type=EventNames.ALERT_CREATED,
        payload={
            "alert_id": alert.pk,
            "owner_id": alert.owner_id,
            "type": alert.type,
            "category": alert.category,
            "severity": alert.severity,
            "source": alert.source,
        },
        metadata={
            "context": EventContext.ALERTS.value,
            "source": source,
            "correlation_id": correlation_id or alert.correlation_id,
            "aggregate_type": "alert",
            "aggregate_id": str(alert.pk),
        },
        priority=EventPriority.NORMAL,
        correlation_id=correlation_id or alert.correlation_id,
    )

    # 2) Enriquecimiento IA (no bloquea la creación de la alerta)
    #    Por ahora se hace in-process. Más adelante puedes:
    #      - Mover esto a un listener de ALERT_CREATED (desacoplar IA del core).
    #      - Delegarlo a un microservicio LLM que escuche en Kafka/cola
    #        y luego llame a PATCH /alerts/{id}/enrich/.
    return alert


# ========= REGLAS DE BALANCE / GASTO =========


def evaluate_balance_alerts_for_account(
    *,
    account,
    old_balance: Decimal,
    new_balance: Decimal,
    reason: str,
    transaction_id: Optional[int] = None,
    triggered_at=None,
    correlation_id: Optional[str] = None,
) -> List[Alert]:
    """
    Evalúa reglas de alertas basadas en cambios de balance de una cuenta.

    Se llama normalmente desde alerts.event_handlers.handle_account_balance_updated(),
    que escucha el evento ACCOUNT_BALANCE_UPDATED emitido por accounts.signals.

    Reglas actuales:
      - Límite mensual de gasto (over_spend) usando transactions.utils_limits.account_month_expense_total.

    Posibles reglas futuras (dejamos el comentario para orientarte):
      - low_balance:
          Si new_balance < umbral (por tipo de cuenta o por preferencia del usuario),
          crear una alerta AlertType.LOW_BALANCE con categoría CASHFLOW o RISK.
      - unusual_activity:
          Si |new_balance - old_balance| > cierto múltiplo de la desviación estándar
          de movimientos normales del usuario.
      - goal_drift:
          Si el gasto de una categoría está alejando al usuario de su meta (goals).

    Todas las alertas que se generen aquí pasan por create_alert(), así que:
      - Publican ALERT_CREATED.
      - Se enriquecen con IA (ALERT_AI_ENRICHED).
    """
    from finance.transactions.utils_limits import account_month_expense_total  # import local para evitar ciclos

    triggered_at = triggered_at or timezone.now()
    alerts: List[Alert] = []

    owner = getattr(account, "owner", None)
    if not owner:
        logger.debug(
            "[alerts] Cuenta id=%s sin owner, no se generan alertas.",
            account.pk,
        )
        return alerts

    # --- Regla: límite mensual de gasto (over_spend) ---
    monthly_limit = getattr(account, "monthly_expense_limit", None)
    lock_on_limit = getattr(account, "lock_on_limit", False)

    if monthly_limit and not lock_on_limit:
        try:
            month_total = account_month_expense_total(account, triggered_at.date())
        except Exception as e:
            logger.error(
                "[alerts] Error calculando account_month_expense_total para account_id=%s: %s",
                account.pk,
                e,
                exc_info=True,
            )
            month_total = None

        if month_total is not None and Decimal(month_total) > Decimal(monthly_limit):
            title = f"Límite de gasto mensual superado en {account.name}"
            message = (
                f"Has gastado {month_total} {account.currency} este mes en la cuenta "
                f"{account.name}, superando el límite definido de "
                f"{monthly_limit} {account.currency}."
            )
            payload = {
                "account_id": account.pk,
                "account_name": account.name,
                "currency": account.currency,
                "month_total": float(month_total),
                "limit": float(monthly_limit),
                "transaction_id": transaction_id,
                "triggered_at": triggered_at.isoformat(),
                "reason": reason,
            }

            alerts.append(
                create_alert(
                    owner=owner,
                    type=AlertType.OVER_SPEND,
                    title=title,
                    message=message,
                    category=AlertCategory.SPENDING,
                    severity=AlertSeverity.WARNING,
                    payload=payload,
                    source="alerts.services.evaluate_balance_alerts_for_account",
                    correlation_id=correlation_id,
                )
            )

    # ====== EJEMPLOS FUTUROS (comentados) ======
    #
    # 1) low_balance básico
    #
    #   low_balance_threshold = getattr(account, "low_balance_threshold", None)
    #   if low_balance_threshold is not None and new_balance < Decimal(low_balance_threshold):
    #       title = f"Saldo bajo en {account.name}"
    #       message = (
    #           f"Tu saldo en {account.name} es de {new_balance} {account.currency}, "
    #           f"por debajo del umbral configurado de {low_balance_threshold} {account.currency}."
    #       )
    #       payload = {
    #           "account_id": account.pk,
    #           "account_name": account.name,
    #           "currency": account.currency,
    #           "balance": float(new_balance),
    #           "threshold": float(low_balance_threshold),
    #           "triggered_at": triggered_at.isoformat(),
    #           "reason": reason,
    #       }
    #       alerts.append(
    #           create_alert(
    #               owner=owner,
    #               type=AlertType.LOW_BALANCE,
    #               title=title,
    #               message=message,
    #               category=AlertCategory.CASHFLOW,
    #               severity=AlertSeverity.INFO,
    #               payload=payload,
    #               source="alerts.services.evaluate_balance_alerts_for_account",
    #               correlation_id=correlation_id,
    #           )
    #       )
    #
    # 2) unusual_activity (bosquejo)
    #
    #   # Podrías calcular una media y desviación estándar de los movimientos de
    #   # los últimos N días y, si el delta supera X desviaciones, disparar una alerta
    #   # de riesgo/anomalía. Eso alimentaría al CFO virtual y a módulos de seguridad.

    return alerts


# ========= ALERTAS POR PAGOS PROGRAMADOS =========


def _generate_scheduled_payment_alerts_legacy_shadow(
    *,
    days_ahead: int = 3,
) -> int:
    """
    Placeholder historico sin rol operativo.

    Se conserva temporalmente para no romper imports viejos, pero el flujo
    canonico de alertas de pagos programados vive en
    `generate_scheduled_payment_alerts(...)` y usa solo `PaymentScheduleRun`.
    """
    return generate_scheduled_payment_alerts(days_ahead=days_ahead)
def generate_scheduled_payment_alerts(
    *,
    days_ahead: int = 3,
) -> int:
    """Genera alertas de pagos programados proximos usando `PaymentScheduleRun`."""
    from datetime import timedelta

    from payments.scheduled_payments.models import PaymentScheduleRun

    now = timezone.now().date()
    cutoff = now + timedelta(days=days_ahead)

    qs = PaymentScheduleRun.objects.filter(
        status__in=[
            PaymentScheduleRun.Status.SCHEDULED,
            PaymentScheduleRun.Status.DUE,
            PaymentScheduleRun.Status.POSTPONED,
        ],
        due_on__gte=now,
        due_on__lte=cutoff,
    )

    count = 0

    for run in qs.select_related("owner", "template", "template__account"):
        template = run.template
        owner = run.owner
        account = getattr(template, "account", None)
        amount = run.expected_amount or template.default_amount or 0
        currency = run.expected_currency or template.currency or "COP"

        payload = {
            "payment_schedule_run_id": run.pk,
            "payment_template_id": template.pk,
            "name": template.name,
            "amount": float(amount),
            "currency": currency,
            "due_date": run.due_on.isoformat(),
            "account_id": getattr(account, "pk", None),
            "account_name": getattr(account, "name", None),
        }

        create_alert(
            owner=owner,
            type=AlertType.SCHEDULED_PAYMENT_DUE,
            title=f"Pago programado proximo: {template.name}",
            message=f"Tienes un pago programado de {amount} {currency} que vence el {run.due_on}.",
            category=AlertCategory.CASHFLOW,
            severity=AlertSeverity.INFO,
            payload=payload,
            source="alerts.services.generate_scheduled_payment_alerts",
        )

        count += 1

    logger.info("[alerts] generate_scheduled_payment_alerts moderno creo %s alertas (days_ahead=%s)", count, days_ahead)
    return count
