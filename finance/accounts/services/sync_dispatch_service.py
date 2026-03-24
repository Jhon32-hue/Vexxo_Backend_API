"""
Orquestacion opcional de syncs de cuentas hacia Google Cloud Tasks.

Descripcion general:
- transforma eventos del dominio `accounts` en tareas HTTP para workers
  externos
- permite que el backend financiero siga siendo la fuente de verdad mientras
  la ejecucion de sync vive fuera del monolito

Analisis detallado:
- el evento `accounts.sync.scheduled.v1` expresa la intencion de ejecutar un
  sync; este servicio la materializa como una Cloud Task cuando hay
  configuracion GCP disponible
- la tarea apunta tipicamente a un servicio de integraciones en Cloud Run
- si falta configuracion o dependencias, el servicio no rompe el flujo local;
  solo retorna `None` y deja trazabilidad en logs
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings

logger = logging.getLogger(__name__)


def sync_cloud_tasks_ready() -> bool:
    return bool(
        getattr(settings, "ACCOUNTS_SYNC_CLOUD_TASKS_ENABLED", False)
        and getattr(settings, "GCP_PROJECT_ID", "")
        and getattr(settings, "ACCOUNTS_SYNC_CLOUD_TASKS_QUEUE", "")
        and getattr(settings, "ACCOUNTS_SYNC_HANDLER_URL", "")
    )


def _parse_event_schedule(payload: dict) -> datetime | None:
    raw = (payload or {}).get("next_sync_at")
    if not raw:
        return None

    try:
        normalized = str(raw).replace("Z", "+00:00")
        scheduled_at = datetime.fromisoformat(normalized)
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=dt_timezone.utc)
        return scheduled_at.astimezone(dt_timezone.utc)
    except Exception:
        logger.warning("[accounts.sync] No se pudo parsear next_sync_at=%s para Cloud Tasks.", raw)
        return None


def enqueue_account_sync_task(*, event, task_name_suffix: str | None = None):
    if not sync_cloud_tasks_ready():
        logger.info("[accounts.sync] Cloud Tasks no esta habilitado o le falta configuracion.")
        return None

    try:
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
        from google.api_core.exceptions import AlreadyExists
    except Exception:
        logger.warning(
            "[accounts.sync] Cloud Tasks configurado, pero falta la dependencia "
            "`google-cloud-tasks`."
        )
        return None

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        settings.GCP_PROJECT_ID,
        settings.ACCOUNTS_SYNC_CLOUD_TASKS_LOCATION,
        settings.ACCOUNTS_SYNC_CLOUD_TASKS_QUEUE,
    )

    body = json.dumps(
        {
            "event": event.to_dict(),
            "account_id": (event.payload or {}).get("account_id"),
            "provider": (event.payload or {}).get("provider"),
            "next_sync_at": (event.payload or {}).get("next_sync_at"),
        },
        default=str,
    ).encode("utf-8")

    http_request = {
        "http_method": tasks_v2.HttpMethod.POST,
        "url": settings.ACCOUNTS_SYNC_HANDLER_URL,
        "headers": {
            "Content-Type": "application/json",
            "X-Vexxo-Event-Type": event.type,
            "X-Vexxo-Context": event.context.value,
        },
        "body": body,
    }

    if getattr(settings, "ACCOUNTS_SYNC_INTERNAL_TOKEN", ""):
        http_request["headers"]["X-Vexxo-Internal-Token"] = settings.ACCOUNTS_SYNC_INTERNAL_TOKEN

    if settings.ACCOUNTS_SYNC_TASK_SERVICE_ACCOUNT_EMAIL:
        http_request["oidc_token"] = {
            "service_account_email": settings.ACCOUNTS_SYNC_TASK_SERVICE_ACCOUNT_EMAIL,
            "audience": settings.ACCOUNTS_SYNC_TASK_AUDIENCE or settings.ACCOUNTS_SYNC_HANDLER_URL,
        }

    task = {"http_request": http_request}

    scheduled_at = _parse_event_schedule(event.payload or {})
    if scheduled_at is None:
        scheduled_at = datetime.now(dt_timezone.utc) + timedelta(
            seconds=max(0, int(settings.ACCOUNTS_SYNC_TASK_BUFFER_SECONDS))
        )

    ts = timestamp_pb2.Timestamp()
    ts.FromDatetime(scheduled_at)
    task["schedule_time"] = ts

    if task_name_suffix:
        safe_suffix = str(task_name_suffix).replace("/", "-").replace(":", "-")
        task["name"] = f"{parent}/tasks/accounts-sync-{safe_suffix}"

    try:
        response = client.create_task(request={"parent": parent, "task": task})
    except AlreadyExists:
        logger.info(
            "[accounts.sync] La Cloud Task ya existia para account_id=%s; se evita duplicado.",
            (event.payload or {}).get("account_id"),
        )
        return None
    logger.info(
        "[accounts.sync] Cloud Task creada para account_id=%s task=%s",
        (event.payload or {}).get("account_id"),
        getattr(response, "name", ""),
    )
    return response
