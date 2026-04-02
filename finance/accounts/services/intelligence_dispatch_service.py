"""
Orquestacion opcional de proyecciones de inteligencia hacia Google Cloud Tasks.

Descripcion general:
- transforma eventos de `accounts` en tareas HTTP para recalcular snapshots y
  senales derivadas fuera del proceso web
- evita que la inteligencia de cuentas crezca dentro del request-response path
- permite que workers externos reporten `started/completed/failed` sin quedar
  acoplados al fallback local actual

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
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def intelligence_cloud_tasks_ready() -> bool:
    return bool(
        getattr(settings, "ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_ENABLED", False)
        and getattr(settings, "GCP_PROJECT_ID", "")
        and getattr(settings, "ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_QUEUE", "")
        and getattr(settings, "ACCOUNTS_INTELLIGENCE_HANDLER_URL", "")
    )


def _coalesce_window_seconds() -> int:
    return max(5, int(getattr(settings, "ACCOUNTS_INTELLIGENCE_COALESCE_SECONDS", 30)))


def _request_event_details(event=None, *, source: str = "") -> dict:
    return {
        "event_type": str(getattr(event, "type", "") or ""),
        "correlation_id": str(getattr(event, "correlation_id", None) or ""),
        "source": str(source or getattr(event, "type", "") or "accounts.intelligence_dispatch"),
    }


def _load_dispatch_state(*, owner_id):
    from finance.accounts.models import AccountIntelligenceDispatchState

    state = (
        AccountIntelligenceDispatchState.objects.select_for_update()
        .filter(owner_id=owner_id)
        .first()
    )
    if state is None:
        state = AccountIntelligenceDispatchState(owner_id=owner_id)
    return state


def _task_matches(state, *, task_name: str = "") -> bool:
    expected = str(getattr(state, "last_task_name", "") or "").strip()
    current = str(task_name or "").strip()
    if not expected or not current:
        return True
    return expected == current


def request_account_intelligence_refresh(*, owner_id: str | int | None, event=None, source: str = "", force: bool = False) -> dict:
    if not owner_id:
        return {"should_dispatch": False, "result": "owner_missing"}

    details = _request_event_details(event, source=source)
    now = timezone.now()
    window_seconds = _coalesce_window_seconds()

    with transaction.atomic():
        state = _load_dispatch_state(owner_id=owner_id)

        recent_points = [
            dt
            for dt in [state.last_requested_at, state.last_enqueued_at, state.last_completed_at]
            if dt is not None
        ]
        recent_reference = max(recent_points) if recent_points else None
        should_dispatch = bool(force)
        if not should_dispatch:
            should_dispatch = not (
                recent_reference is not None
                and max(0, int((now - recent_reference).total_seconds())) < window_seconds
            )

        state.pending_request = True
        state.request_count = int(state.request_count or 0) + 1
        state.last_requested_at = now
        state.last_event_type = details["event_type"][:128]
        state.last_source = details["source"][:128]
        state.last_correlation_id = details["correlation_id"][:64]
        state.last_result = "requested" if should_dispatch else "coalesced"
        state.last_error_message = ""
        state.save()

    return {
        "should_dispatch": should_dispatch,
        "result": state.last_result,
        "window_seconds": window_seconds,
    }


def mark_account_intelligence_refresh_enqueued(*, owner_id: str | int | None, task_name: str = "", result: str = "enqueued") -> None:
    from finance.accounts.models import AccountIntelligenceDispatchState

    if not owner_id:
        return
    AccountIntelligenceDispatchState.objects.filter(owner_id=owner_id).update(
        pending_request=True,
        last_enqueued_at=timezone.now(),
        last_task_name=(task_name or "")[:255],
        last_result=(result or "enqueued")[:64],
        last_error_message="",
    )


def mark_account_intelligence_refresh_started(*, owner_id: str | int | None, task_name: str = "", result: str = "started") -> dict:
    if not owner_id:
        return {"applied": False, "result": "owner_missing"}

    with transaction.atomic():
        state = _load_dispatch_state(owner_id=owner_id)
        if not _task_matches(state, task_name=task_name):
            return {
                "applied": False,
                "result": "stale_task",
                "expected_task_name": str(getattr(state, "last_task_name", "") or ""),
            }

        now = timezone.now()
        state.pending_request = True
        state.last_started_at = now
        if task_name:
            state.last_task_name = str(task_name)[:255]
        state.last_result = (result or "started")[:64]
        state.last_error_message = ""
        state.save()

    return {"applied": True, "result": state.last_result}


def mark_account_intelligence_refresh_completed(*, owner_id: str | int | None, result: str = "completed") -> None:
    from finance.accounts.models import AccountIntelligenceDispatchState

    if not owner_id:
        return
    AccountIntelligenceDispatchState.objects.filter(owner_id=owner_id).update(
        pending_request=False,
        last_completed_at=timezone.now(),
        last_result=(result or "completed")[:64],
        last_error_message="",
    )


def mark_account_intelligence_refresh_blocked(*, owner_id: str | int | None, result: str = "blocked") -> None:
    from finance.accounts.models import AccountIntelligenceDispatchState

    if not owner_id:
        return
    AccountIntelligenceDispatchState.objects.filter(owner_id=owner_id).update(
        pending_request=True,
        last_result=(result or "blocked")[:64],
    )


def mark_account_intelligence_refresh_failed(
    *,
    owner_id: str | int | None,
    task_name: str = "",
    result: str = "failed",
    error_message: str = "",
) -> dict:
    if not owner_id:
        return {"applied": False, "result": "owner_missing"}

    with transaction.atomic():
        state = _load_dispatch_state(owner_id=owner_id)
        if not _task_matches(state, task_name=task_name):
            return {
                "applied": False,
                "result": "stale_task",
                "expected_task_name": str(getattr(state, "last_task_name", "") or ""),
            }

        now = timezone.now()
        state.pending_request = False
        state.last_failed_at = now
        if task_name:
            state.last_task_name = str(task_name)[:255]
        state.last_result = (result or "failed")[:64]
        state.last_error_message = str(error_message or "")[:2000]
        state.save()

    return {"applied": True, "result": state.last_result}


def report_account_intelligence_worker_status(
    *,
    owner_id: str | int | None,
    status: str,
    task_name: str = "",
    result: str = "",
    error_message: str = "",
) -> dict:
    normalized_status = str(status or "").strip().lower()
    if normalized_status == "started":
        return mark_account_intelligence_refresh_started(
            owner_id=owner_id,
            task_name=task_name,
            result=result or "started",
        )
    if normalized_status == "completed":
        report = mark_account_intelligence_refresh_completed_for_task(
            owner_id=owner_id,
            task_name=task_name,
            result=result or "completed",
        )
        return report
    if normalized_status == "failed":
        return mark_account_intelligence_refresh_failed(
            owner_id=owner_id,
            task_name=task_name,
            result=result or "failed",
            error_message=error_message,
        )
    return {"applied": False, "result": "invalid_status"}


def mark_account_intelligence_refresh_completed_for_task(
    *,
    owner_id: str | int | None,
    task_name: str = "",
    result: str = "completed",
) -> dict:
    if not owner_id:
        return {"applied": False, "result": "owner_missing"}

    with transaction.atomic():
        state = _load_dispatch_state(owner_id=owner_id)
        if not _task_matches(state, task_name=task_name):
            return {
                "applied": False,
                "result": "stale_task",
                "expected_task_name": str(getattr(state, "last_task_name", "") or ""),
            }

        now = timezone.now()
        state.pending_request = False
        state.last_completed_at = now
        if task_name:
            state.last_task_name = str(task_name)[:255]
        state.last_result = (result or "completed")[:64]
        state.last_error_message = ""
        state.save()

    return {"applied": True, "result": state.last_result}


def dispatch_account_intelligence_refresh(
    *,
    owner_id: str | int | None,
    event=None,
    source: str = "",
    task_name_suffix: str | None = None,
    force: bool = False,
) -> dict:
    request = request_account_intelligence_refresh(
        owner_id=owner_id,
        event=event,
        source=source,
        force=force,
    )
    if not request["should_dispatch"]:
        return request

    response = enqueue_account_intelligence_refresh_task(
        event=event,
        owner_id=owner_id,
        task_name_suffix=task_name_suffix,
        source=source,
    )
    if response is not None:
        mark_account_intelligence_refresh_enqueued(
            owner_id=owner_id,
            task_name=getattr(response, "name", ""),
            result="enqueued",
        )
        return {**request, "result": "enqueued", "task_name": getattr(response, "name", "")}

    if account_intelligence_local_fallback_allowed():
        from finance.accounts.services.intelligence_service import refresh_account_intelligence_for_user

        refresh_account_intelligence_for_user(owner_id)
        mark_account_intelligence_refresh_completed(owner_id=owner_id, result="local_fallback")
        return {**request, "result": "local_fallback"}

    mark_account_intelligence_refresh_blocked(owner_id=owner_id, result="pipeline_unavailable")
    return {**request, "result": "pipeline_unavailable"}


def get_account_intelligence_projection_status(*, owner) -> dict:
    from finance.accounts.models import (
        AccountIntelligenceDispatchState,
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
    dispatch_state = AccountIntelligenceDispatchState.objects.filter(owner=owner).first()
    pending = (
        portfolio is None
        or risk is None
        or owner_metrics is None
        or bool(getattr(dispatch_state, "pending_request", False))
    )
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
        "dispatch_pending": bool(getattr(dispatch_state, "pending_request", False)),
        "dispatch_last_requested_at": dispatch_state.last_requested_at.isoformat() if getattr(dispatch_state, "last_requested_at", None) else None,
        "dispatch_last_enqueued_at": dispatch_state.last_enqueued_at.isoformat() if getattr(dispatch_state, "last_enqueued_at", None) else None,
        "dispatch_last_started_at": dispatch_state.last_started_at.isoformat() if getattr(dispatch_state, "last_started_at", None) else None,
        "dispatch_last_completed_at": dispatch_state.last_completed_at.isoformat() if getattr(dispatch_state, "last_completed_at", None) else None,
        "dispatch_last_failed_at": dispatch_state.last_failed_at.isoformat() if getattr(dispatch_state, "last_failed_at", None) else None,
        "dispatch_last_task_name": str(getattr(dispatch_state, "last_task_name", "") or ""),
        "dispatch_last_result": str(getattr(dispatch_state, "last_result", "") or ""),
        "dispatch_last_error_message": str(getattr(dispatch_state, "last_error_message", "") or ""),
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
