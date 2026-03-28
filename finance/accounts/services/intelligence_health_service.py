"""
Salud operativa y alertas de proyecciones async de `accounts`.

Descripcion general:
- evalua si los snapshots/materializaciones de inteligencia existen, estan
  pendientes demasiado tiempo o quedaron stale
- expone una lectura operativa consumible por API, soporte y dashboards
- puede generar alertas deduplicadas para que el problema no quede solo en logs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

from finance.accounts.services.intelligence_dispatch_service import get_account_intelligence_projection_status

logger = logging.getLogger(__name__)

PROJECTION_ALERT_SOURCE = "accounts.intelligence.health"
ALERT_PENDING_TITLE = "Proyeccion de cuentas pendiente"
ALERT_STALE_TITLE = "Proyeccion de cuentas desactualizada"
ALERT_PIPELINE_TITLE = "Pipeline de proyecciones no disponible"


def _seconds_since_reference(owner, *, latest_generated_at) -> int | None:
    if latest_generated_at is not None:
        return max(0, int((timezone.now() - latest_generated_at).total_seconds()))
    reference = getattr(owner, "date_joined", None)
    if reference is None:
        return None
    return max(0, int((timezone.now() - reference).total_seconds()))


def _find_active_operational_alert(owner, *, title: str):
    from alerts.alerts.models.alerts import Alert, AlertType

    return (
        Alert.objects.filter(
            owner=owner,
            source=PROJECTION_ALERT_SOURCE,
            type=AlertType.SYSTEM,
            title=title,
            is_active=True,
        )
        .order_by("-created_at")
        .first()
    )


def _ensure_operational_alert(owner, *, title: str, message: str, severity: str, health_code: str) -> None:
    from alerts.alerts.models.alerts import AlertCategory, AlertStatus, AlertType

    alert = _find_active_operational_alert(owner, title=title)
    if alert is not None:
        updated = False
        if alert.message != message:
            alert.message = message
            updated = True
        if alert.severity != severity:
            alert.severity = severity
            updated = True
        payload = dict(alert.payload or {})
        if payload.get("health_code") != health_code:
            payload["health_code"] = health_code
            alert.payload = payload
            updated = True
        if updated:
            alert.save(update_fields=["message", "severity", "payload", "updated_at"])
        return

    from alerts.alerts.models.alerts import Alert

    Alert.objects.create(
        owner=owner,
        type=AlertType.SYSTEM,
        category=AlertCategory.SYSTEM,
        severity=severity,
        status=AlertStatus.NEW,
        title=title,
        message=message,
        payload={"health_code": health_code},
        source=PROJECTION_ALERT_SOURCE,
        correlation_id="",
        is_active=True,
    )


def _resolve_operational_alert(owner, *, title: str) -> None:
    alert = _find_active_operational_alert(owner, title=title)
    if alert is not None:
        alert.mark_resolved(commit=True)


def sync_projection_operational_alerts(*, owner, health: dict) -> list[str]:
    if not bool(getattr(settings, "ACCOUNTS_INTELLIGENCE_ALERTS_ENABLED", True)):
        return []

    active_codes: list[str] = []

    if health["pipeline_unavailable"]:
        _ensure_operational_alert(
            owner,
            title=ALERT_PIPELINE_TITLE,
            message=(
                "La inteligencia de cuentas no puede materializarse porque no hay "
                "pipeline async disponible ni fallback local habilitado."
            ),
            severity="critical",
            health_code="pipeline_unavailable",
        )
        active_codes.append("pipeline_unavailable")
    else:
        _resolve_operational_alert(owner, title=ALERT_PIPELINE_TITLE)

    if health["pending_too_long"]:
        _ensure_operational_alert(
            owner,
            title=ALERT_PENDING_TITLE,
            message=(
                "Las proyecciones de cuentas siguen pendientes mas tiempo del "
                "umbral operativo esperado."
            ),
            severity="warning",
            health_code="pending_too_long",
        )
        active_codes.append("pending_too_long")
    else:
        _resolve_operational_alert(owner, title=ALERT_PENDING_TITLE)

    if health["stale"]:
        _ensure_operational_alert(
            owner,
            title=ALERT_STALE_TITLE,
            message=(
                "Las proyecciones de cuentas estan materializadas, pero ya se "
                "consideran stale para operacion y dashboards."
            ),
            severity="warning" if not health["pending"] else "critical",
            health_code="stale",
        )
        active_codes.append("stale")
    else:
        _resolve_operational_alert(owner, title=ALERT_STALE_TITLE)

    return sorted(active_codes)


def get_account_intelligence_operational_health(*, owner, sync_alerts: bool = False) -> dict:
    projection_status = get_account_intelligence_projection_status(owner=owner)
    pending_threshold_seconds = int(
        getattr(settings, "ACCOUNTS_INTELLIGENCE_MAX_PENDING_SECONDS", 900)
    )
    stale_threshold_seconds = int(
        getattr(settings, "ACCOUNTS_INTELLIGENCE_STALE_AFTER_SECONDS", 86400)
    )

    latest_generated_at = None
    if projection_status.get("latest_generated_at"):
        latest_generated_at = datetime.fromisoformat(projection_status["latest_generated_at"])
        if timezone.is_naive(latest_generated_at):
            latest_generated_at = timezone.make_aware(latest_generated_at, dt_timezone.utc)

    effective_age_seconds = _seconds_since_reference(
        owner,
        latest_generated_at=latest_generated_at,
    )
    pending = bool(projection_status["pending"])
    pending_too_long = bool(
        pending
        and effective_age_seconds is not None
        and effective_age_seconds >= pending_threshold_seconds
    )
    stale = bool(
        effective_age_seconds is not None
        and effective_age_seconds >= stale_threshold_seconds
    )
    pipeline_unavailable = bool(
        pending
        and not projection_status["cloud_tasks_ready"]
        and not projection_status["local_fallback_allowed"]
    )

    health_level = "healthy"
    if pipeline_unavailable:
        health_level = "critical"
    elif pending_too_long:
        health_level = "warning"
    elif stale:
        health_level = "warning"
    elif pending:
        health_level = "pending"

    response = {
        "health_level": health_level,
        "pending": pending,
        "pending_too_long": pending_too_long,
        "stale": stale,
        "pipeline_unavailable": pipeline_unavailable,
        "cloud_tasks_ready": bool(projection_status["cloud_tasks_ready"]),
        "local_fallback_allowed": bool(projection_status["local_fallback_allowed"]),
        "latest_generated_at": projection_status["latest_generated_at"],
        "effective_age_seconds": effective_age_seconds,
        "pending_threshold_seconds": pending_threshold_seconds,
        "stale_threshold_seconds": stale_threshold_seconds,
        "alerting_enabled": bool(getattr(settings, "ACCOUNTS_INTELLIGENCE_ALERTS_ENABLED", True)),
        "portfolio_present": bool(projection_status["portfolio_present"]),
        "risk_present": bool(projection_status["risk_present"]),
        "owner_metrics_present": bool(projection_status["owner_metrics_present"]),
    }

    if health_level != "healthy":
        logger.warning(
            "[accounts.intelligence] operational health=%s owner_id=%s pending=%s stale=%s pipeline_unavailable=%s age_seconds=%s",
            health_level,
            owner.pk,
            pending,
            stale,
            pipeline_unavailable,
            effective_age_seconds,
        )

    response["active_alert_codes"] = (
        sync_projection_operational_alerts(owner=owner, health=response)
        if sync_alerts
        else []
    )
    return response
