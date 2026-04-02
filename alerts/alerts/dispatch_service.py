"""
Despacho asincrono de enriquecimiento de alertas con IA.

Objetivo:
- sacar la llamada de IA del flujo directo de request y de listeners en threads
- permitir Cloud Tasks / worker HTTP interno con fallback local controlado
- dejar el modulo listo para migrar despues a un llm_gateway dedicado
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings

logger = logging.getLogger(__name__)


def alerts_ai_cloud_tasks_ready() -> bool:
    return bool(
        getattr(settings, "ALERTS_AI_CLOUD_TASKS_ENABLED", False)
        and getattr(settings, "GCP_PROJECT_ID", "")
        and getattr(settings, "ALERTS_AI_CLOUD_TASKS_QUEUE", "")
        and getattr(settings, "ALERTS_AI_HANDLER_URL", "")
    )


def alerts_ai_local_fallback_allowed() -> bool:
    env_value = str(getattr(settings, "ENV", "local")).strip().lower()
    if env_value in {"prod", "production", "cloud"} and not bool(getattr(settings, "DEBUG", False)):
        return False
    return bool(getattr(settings, "ALERTS_AI_LOCAL_FALLBACK_ENABLED", True))


def _scheduled_time() -> datetime:
    return datetime.now(dt_timezone.utc) + timedelta(
        seconds=max(0, int(getattr(settings, "ALERTS_AI_TASK_BUFFER_SECONDS", 5)))
    )


def enqueue_alert_ai_task(*, alert_id, correlation_id: str = "", source: str = ""):
    if not alert_id or not alerts_ai_cloud_tasks_ready():
        return None

    try:
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
    except Exception:
        logger.warning("[alerts.ai] Cloud Tasks configurado, pero falta `google-cloud-tasks`.")
        return None

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        settings.GCP_PROJECT_ID,
        settings.ALERTS_AI_CLOUD_TASKS_LOCATION,
        settings.ALERTS_AI_CLOUD_TASKS_QUEUE,
    )

    body = json.dumps(
        {
            "alert_id": str(alert_id),
            "correlation_id": str(correlation_id or ""),
            "source": str(source or "alerts.alerts.dispatch_service"),
        },
        default=str,
    ).encode("utf-8")

    http_request = {
        "http_method": tasks_v2.HttpMethod.POST,
        "url": settings.ALERTS_AI_HANDLER_URL,
        "headers": {
            "Content-Type": "application/json",
            "X-Vexxo-Internal-Token": str(getattr(settings, "ALERTS_AI_INTERNAL_TOKEN", "") or ""),
        },
        "body": body,
    }

    if getattr(settings, "ALERTS_AI_TASK_SERVICE_ACCOUNT_EMAIL", ""):
        http_request["oidc_token"] = {
            "service_account_email": settings.ALERTS_AI_TASK_SERVICE_ACCOUNT_EMAIL,
            "audience": getattr(settings, "ALERTS_AI_TASK_AUDIENCE", "") or settings.ALERTS_AI_HANDLER_URL,
        }

    task = {"http_request": http_request}
    ts = timestamp_pb2.Timestamp()
    ts.FromDatetime(_scheduled_time())
    task["schedule_time"] = ts
    task["name"] = f"{parent}/tasks/alerts-ai-{alert_id}"

    try:
        return client.create_task(request={"parent": parent, "task": task})
    except AlreadyExists:
        logger.info("[alerts.ai] Task ya existente para alert_id=%s", alert_id)
        return None


def dispatch_alert_ai_enrichment(*, alert_id, correlation_id: str = "", source: str = "") -> dict:
    if not alert_id:
        return {"result": "missing_alert_id"}

    response = enqueue_alert_ai_task(
        alert_id=alert_id,
        correlation_id=correlation_id,
        source=source,
    )
    if response is not None:
        return {"result": "enqueued", "task_name": getattr(response, "name", "")}

    if not alerts_ai_local_fallback_allowed():
        return {"result": "pipeline_unavailable"}

    from alerts.alerts.models.alerts import Alert
    from alerts.alerts.ai_services import enrich_alert_with_ai

    alert = Alert.objects.filter(pk=alert_id).first()
    if alert is None:
        return {"result": "missing_alert"}

    enrich_alert_with_ai(alert, correlation_id=correlation_id or None)
    return {"result": "local_fallback"}
