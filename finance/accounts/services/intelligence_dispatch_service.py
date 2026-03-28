"""
Orquestacion opcional de proyecciones de inteligencia hacia Google Cloud Tasks.

Descripcion general:
- transforma eventos de `accounts` en tareas HTTP para recalcular snapshots y
  senales derivadas fuera del proceso web
- evita que la inteligencia de cuentas crezca dentro del request-response path

Analisis detallado:
- la capa de inteligencia debe evolucionar como proyeccion asyncrona
- este servicio mantiene el mismo patron que `sync_dispatch_service`, pero para
  read models y snapshots de portfolio/risk/product fit
- si no hay configuracion o dependencias cloud, el modulo puede hacer fallback
  local controlado sin romper el dominio
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def intelligence_cloud_tasks_ready() -> bool:
    return bool(
        getattr(settings, "ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_ENABLED", False)
        and getattr(settings, "GCP_PROJECT_ID", "")
        and getattr(settings, "ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_QUEUE", "")
        and getattr(settings, "ACCOUNTS_INTELLIGENCE_HANDLER_URL", "")
    )


def get_account_intelligence_projection_status(*, owner) -> dict:
    from finance.accounts.models import (
        AccountOwnerMetrics,
        AccountPortfolioSnapshot,
        AccountRiskSnapshot,
    )

    portfolio = AccountPortfolioSnapshot.objects.filter(owner=owner).order_by("-generated_at").first()
    risk = AccountRiskSnapshot.objects.filter(owner=owner).order_by("-generated_at").first()
    owner_metrics = AccountOwnerMetrics.objects.filter(owner=owner).order_by("-generated_at").first()
    latest_generated_at = max(
        [dt for dt in [getattr(portfolio, "generated_at", None), getattr(risk, "generated_at", None), getattr(owner_metrics, "generated_at", None)] if dt is not None],
        default=None,
    )
    pending = portfolio is None or risk is None or owner_metrics is None
    age_seconds = None
    if latest_generated_at is not None:
        age_seconds = max(0, int((timezone.now() - latest_generated_at).total_seconds()))
    return {
        "pending": bool(pending),
        "cloud_tasks_ready": bool(intelligence_cloud_tasks_ready()),
        "local_fallback_allowed": bool(account_intelligence_local_fallback_allowed()),
        "latest_generated_at": latest_generated_at.isoformat() if latest_generated_at else None,
        "age_seconds": age_seconds,
        "portfolio_present": bool(portfolio is not None),
        "risk_present": bool(risk is not None),
        "owner_metrics_present": bool(owner_metrics is not None),
    }


def account_intelligence_local_fallback_allowed() -> bool:
    env_value = str(getattr(settings, "ENV", "local")).strip().lower()
    if env_value in {"prod", "production", "cloud"} and not bool(getattr(settings, "DEBUG", False)):
        return False
    return bool(getattr(settings, "ACCOUNTS_INTELLIGENCE_LOCAL_FALLBACK_ENABLED", True))


def _event_as_dict(event) -> dict:
    if event is None:
        return {"type": "accounts.intelligence.refresh.requested.v1", "context": "accounts"}
    if hasattr(event, "to_dict"):
        return event.to_dict()
    return {
        "type": getattr(event, "type", "accounts.intelligence.refresh.requested.v1"),
        "context": getattr(getattr(event, "context", None), "value", "accounts"),
        "correlation_id": getattr(event, "correlation_id", None),
        "causation_id": getattr(event, "causation_id", None),
    }


def _scheduled_time() -> datetime:
    return datetime.now(dt_timezone.utc) + timedelta(
        seconds=max(0, int(getattr(settings, "ACCOUNTS_INTELLIGENCE_TASK_BUFFER_SECONDS", 10)))
    )


def enqueue_account_intelligence_refresh_task(*, event=None, owner_id: str | int | None, task_name_suffix: str | None = None, source: str = ""):
    if not owner_id:
        logger.info("[accounts.intelligence] owner_id vacio; no se agenda tarea.")
        return None

    if not intelligence_cloud_tasks_ready():
        logger.info("[accounts.intelligence] Cloud Tasks no esta habilitado o le falta configuracion.")
        return None

    try:
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
    except Exception:
        logger.warning(
            "[accounts.intelligence] Cloud Tasks configurado, pero falta la dependencia "
            "`google-cloud-tasks`."
        )
        return None

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(
        settings.GCP_PROJECT_ID,
        settings.ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_LOCATION,
        settings.ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_QUEUE,
    )

    body = json.dumps(
        {
            "event": _event_as_dict(event),
            "owner_id": str(owner_id),
            "source": source or "accounts.intelligence_dispatch",
        },
        default=str,
    ).encode("utf-8")

    http_request = {
        "http_method": tasks_v2.HttpMethod.POST,
        "url": settings.ACCOUNTS_INTELLIGENCE_HANDLER_URL,
        "headers": {
            "Content-Type": "application/json",
            "X-Vexxo-Event-Type": getattr(event, "type", "accounts.intelligence.refresh.requested.v1"),
            "X-Vexxo-Context": getattr(getattr(event, "context", None), "value", "accounts"),
        },
        "body": body,
    }

    if getattr(settings, "ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN", ""):
        http_request["headers"]["X-Vexxo-Internal-Token"] = settings.ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN

    if settings.ACCOUNTS_INTELLIGENCE_TASK_SERVICE_ACCOUNT_EMAIL:
        http_request["oidc_token"] = {
            "service_account_email": settings.ACCOUNTS_INTELLIGENCE_TASK_SERVICE_ACCOUNT_EMAIL,
            "audience": settings.ACCOUNTS_INTELLIGENCE_TASK_AUDIENCE or settings.ACCOUNTS_INTELLIGENCE_HANDLER_URL,
        }

    task = {"http_request": http_request}

    ts = timestamp_pb2.Timestamp()
    ts.FromDatetime(_scheduled_time())
    task["schedule_time"] = ts

    if task_name_suffix:
        safe_suffix = str(task_name_suffix).replace("/", "-").replace(":", "-")
        task["name"] = f"{parent}/tasks/accounts-intelligence-{safe_suffix}"

    try:
        response = client.create_task(request={"parent": parent, "task": task})
    except AlreadyExists:
        logger.info(
            "[accounts.intelligence] La Cloud Task ya existia para owner_id=%s; se evita duplicado.",
            owner_id,
        )
        return None

    logger.info(
        "[accounts.intelligence] Cloud Task creada para owner_id=%s task=%s",
        owner_id,
        getattr(response, "name", ""),
    )
    return response
