"""
Despacho asincrono de enriquecimiento de alertas con IA.

Objetivo:
- sacar la llamada de IA del flujo directo de request y de listeners en threads
- permitir Cloud Tasks / worker HTTP interno con fallback local controlado
- dejar el modulo listo para migrar despues a un llm_gateway dedicado
"""

from __future__ import annotations

import logging

from django.conf import settings

from alerts.alerts.ai_worker_service import (
    get_or_create_alert_ai_state,
    process_alert_ai_request,
    request_alert_ai_enrichment,
)
from alerts.alerts.models import AlertAiDispatchState
from tasks.async_backends import (
    AsyncExecutionMode,
    CloudTaskDispatchConfig,
    cloud_tasks_ready,
    dispatch_job,
    get_async_execution_fallback_mode,
    get_async_execution_mode,
)

logger = logging.getLogger(__name__)
JOB_TYPE = "alerts.ai"


def alerts_ai_cloud_tasks_ready() -> bool:
    return cloud_tasks_ready(_cloud_task_config(alert_id="", correlation_id="", source=""))

def alerts_ai_execution_mode() -> str:
    return get_async_execution_mode(
        JOB_TYPE,
        cloud_tasks_enabled=alerts_ai_cloud_tasks_ready(),
    )


def alerts_ai_fallback_mode() -> str:
    return get_async_execution_fallback_mode(
        JOB_TYPE,
    )

def _cloud_task_config(*, alert_id, correlation_id: str = "", source: str = "") -> CloudTaskDispatchConfig:
    return CloudTaskDispatchConfig(
        job_type=JOB_TYPE,
        enabled=bool(getattr(settings, "ALERTS_AI_CLOUD_TASKS_ENABLED", False)),
        queue=str(getattr(settings, "ALERTS_AI_CLOUD_TASKS_QUEUE", "") or ""),
        location=str(getattr(settings, "ALERTS_AI_CLOUD_TASKS_LOCATION", "") or ""),
        handler_url=str(getattr(settings, "ALERTS_AI_HANDLER_URL", "") or ""),
        payload={
            "alert_id": str(alert_id or ""),
            "correlation_id": str(correlation_id or ""),
            "source": str(source or "alerts.alerts.dispatch_service"),
        },
        task_name=f"alerts-ai-{alert_id}" if alert_id else "",
        internal_token=str(getattr(settings, "ALERTS_AI_INTERNAL_TOKEN", "") or ""),
        service_account_email=str(getattr(settings, "ALERTS_AI_TASK_SERVICE_ACCOUNT_EMAIL", "") or ""),
        audience=str(getattr(settings, "ALERTS_AI_TASK_AUDIENCE", "") or ""),
        buffer_seconds=max(0, int(getattr(settings, "ALERTS_AI_TASK_BUFFER_SECONDS", 5) or 5)),
    )


def dispatch_alert_ai_enrichment(*, alert_id, correlation_id: str = "", source: str = "", force: bool = False) -> dict:
    if not alert_id:
        return {"result": "missing_alert_id"}

    request = request_alert_ai_enrichment(alert_id=alert_id, force=force)
    if not request.get("should_dispatch"):
        return request

    dispatch_result = dispatch_job(
        job_type=JOB_TYPE,
        cloud_task_config=_cloud_task_config(
            alert_id=alert_id,
            correlation_id=correlation_id,
            source=source,
        ),
        inline_handler=lambda: process_alert_ai_request(
            alert_id=alert_id,
            correlation_id=correlation_id,
            source=source or "alerts.ai.inline",
        ),
    )
    result = str(dispatch_result.get("result") or "")
    state = get_or_create_alert_ai_state(alert_id=alert_id)
    if state is None:
        return {"result": "missing_alert"}

    if result in {"enqueued", "already_enqueued"}:
        state.note_dispatch_attempt(
            backend=AlertAiDispatchState.DispatchBackend.CLOUD_TASKS,
            result=result,
        )
        state.mark_queued(backend=AlertAiDispatchState.DispatchBackend.CLOUD_TASKS)
        if dispatch_result.get("task_name"):
            return {"result": result, "task_name": dispatch_result.get("task_name", "")}
        return {"result": result}

    if result == "local_worker_pending":
        state.note_dispatch_attempt(
            backend=AlertAiDispatchState.DispatchBackend.LOCAL_WORKER,
            result="local_worker_pending",
        )
        state.mark_queued(backend=AlertAiDispatchState.DispatchBackend.LOCAL_WORKER)
        return {"result": "local_worker_pending"}

    if result == "inline_processed":
        state.note_dispatch_attempt(
            backend=AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
            result=result,
        )
        return dispatch_result

    error_message = str(dispatch_result.get("fallback_reason") or dispatch_result.get("error") or "pipeline_unavailable")
    backend = str(dispatch_result.get("dispatch_backend") or "")
    state.note_dispatch_attempt(
        backend=backend or state.dispatch_backend or "",
        result="pipeline_unavailable",
        error=error_message,
    )
    state.mark_dispatch_failed(error=error_message, backend=backend or state.dispatch_backend or "")
    return {"result": "pipeline_unavailable"}
