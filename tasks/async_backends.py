from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Callable

from django.conf import settings

logger = logging.getLogger(__name__)

class AsyncExecutionMode:
    CLOUD_TASKS = "cloud_tasks"
    LOCAL_WORKER = "local_worker"
    SYNC_INLINE_FOR_TESTS = "sync_inline_for_tests"
    DISABLED = "disabled"


_VALID_EXECUTION_MODES = {
    AsyncExecutionMode.CLOUD_TASKS,
    AsyncExecutionMode.LOCAL_WORKER,
    AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
    AsyncExecutionMode.DISABLED,
}

_VALID_FALLBACK_MODES = {
    AsyncExecutionMode.LOCAL_WORKER,
    AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
    AsyncExecutionMode.DISABLED,
}


@dataclass(frozen=True)
class CloudTaskDispatchConfig:
    job_type: str
    enabled: bool
    queue: str
    location: str
    handler_url: str
    payload: dict[str, Any]
    task_name: str = ""
    internal_token: str = ""
    service_account_email: str = ""
    audience: str = ""
    buffer_seconds: int = 0
    scheduled_at: datetime | None = None
    headers: dict[str, str] = field(default_factory=dict)


def _job_suffix(job_type: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9]+", "_", str(job_type or "").strip()).strip("_").upper()
    return raw or "DEFAULT"


def _normalize_mode(value: Any, *, valid_modes: set[str]) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in valid_modes else ""


def _setting_value(name: str, default: Any = "") -> Any:
    return getattr(settings, name, default)


def get_async_execution_mode(
    job_type: str,
    *,
    cloud_tasks_enabled: bool = False,
    local_worker_available: bool = False,
) -> str:
    suffix = _job_suffix(job_type)
    explicit_mode = _normalize_mode(
        _setting_value(f"ASYNC_EXECUTION_MODE_{suffix}", "") or _setting_value("ASYNC_EXECUTION_MODE", ""),
        valid_modes=_VALID_EXECUTION_MODES,
    )
    if explicit_mode:
        return explicit_mode
    if cloud_tasks_enabled:
        return AsyncExecutionMode.CLOUD_TASKS
    if local_worker_available:
        return AsyncExecutionMode.LOCAL_WORKER
    return AsyncExecutionMode.DISABLED


def get_async_execution_fallback_mode(
    job_type: str,
    *,
    local_worker_available: bool = False,
) -> str:
    suffix = _job_suffix(job_type)
    explicit_mode = _normalize_mode(
        _setting_value(f"ASYNC_EXECUTION_FALLBACK_MODE_{suffix}", "")
        or _setting_value("ASYNC_EXECUTION_FALLBACK_MODE", ""),
        valid_modes=_VALID_FALLBACK_MODES,
    )
    if explicit_mode:
        return explicit_mode
    if local_worker_available:
        return AsyncExecutionMode.LOCAL_WORKER
    return AsyncExecutionMode.DISABLED


def cloud_tasks_ready(config: CloudTaskDispatchConfig) -> bool:
    return bool(
        config.enabled
        and _setting_value("GCP_PROJECT_ID", "")
        and config.queue
        and config.location
        and config.handler_url
    )


def _scheduled_time(buffer_seconds: int) -> datetime:
    return datetime.now(dt_timezone.utc) + timedelta(seconds=max(0, int(buffer_seconds or 0)))


def _dispatch_inline(
    *,
    inline_handler: Callable[[], Any] | None = None,
    requested_backend: str = "",
    fallback_reason: str = "",
) -> dict[str, Any]:
    if inline_handler is None:
        return {
            "result": "pipeline_unavailable",
            "dispatch_backend": AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
            "requested_backend": requested_backend or AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
            "fallback_reason": fallback_reason,
        }
    try:
        inline_result = inline_handler()
    except Exception as exc:
        logger.exception("[async.dispatch] inline handler failed requested_backend=%s", requested_backend)
        return {
            "result": "inline_handler_failed",
            "dispatch_backend": AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
            "requested_backend": requested_backend or AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
            "fallback_reason": fallback_reason,
            "error": str(exc),
        }
    return {
        "result": "inline_processed",
        "dispatch_backend": AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
        "requested_backend": requested_backend or AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
        "fallback_reason": fallback_reason,
        "inline_result": inline_result,
    }


def _enqueue_cloud_task(config: CloudTaskDispatchConfig) -> dict[str, Any]:
    if not cloud_tasks_ready(config):
        return {"result": "cloud_tasks_unavailable", "dispatch_backend": AsyncExecutionMode.CLOUD_TASKS}

    try:
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
    except Exception:
        logger.warning("[async.dispatch] Cloud Tasks configurado, pero falta `google-cloud-tasks` job_type=%s", config.job_type)
        return {"result": "cloud_tasks_client_unavailable", "dispatch_backend": AsyncExecutionMode.CLOUD_TASKS}

    headers = {"Content-Type": "application/json", **(config.headers or {})}
    if config.internal_token:
        headers["X-Vexxo-Internal-Token"] = str(config.internal_token)

    body = json.dumps(config.payload or {}, default=str).encode("utf-8")

    try:
        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(
            _setting_value("GCP_PROJECT_ID", ""),
            config.location,
            config.queue,
        )
        http_request = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": config.handler_url,
            "headers": headers,
            "body": body,
        }
        if config.service_account_email:
            http_request["oidc_token"] = {
                "service_account_email": config.service_account_email,
                "audience": config.audience or config.handler_url,
            }

        task = {"http_request": http_request}
        schedule_time = config.scheduled_at or _scheduled_time(config.buffer_seconds)
        if schedule_time.tzinfo is None:
            schedule_time = schedule_time.replace(tzinfo=dt_timezone.utc)
        else:
            schedule_time = schedule_time.astimezone(dt_timezone.utc)
        ts = timestamp_pb2.Timestamp()
        ts.FromDatetime(schedule_time)
        task["schedule_time"] = ts
        task_name = str(config.task_name or "").strip()
        if task_name:
            task["name"] = f"{parent}/tasks/{task_name}"

        response = client.create_task(request={"parent": parent, "task": task})
        return {
            "result": "enqueued",
            "dispatch_backend": AsyncExecutionMode.CLOUD_TASKS,
            "task_name": getattr(response, "name", task.get("name", "")),
        }
    except AlreadyExists:
        logger.info("[async.dispatch] task ya existente job_type=%s task_name=%s", config.job_type, config.task_name)
        return {
            "result": "already_enqueued",
            "dispatch_backend": AsyncExecutionMode.CLOUD_TASKS,
            "task_name": f"{parent}/tasks/{config.task_name}" if config.task_name else "",
        }
    except Exception as exc:
        logger.exception("[async.dispatch] error creando Cloud Task job_type=%s", config.job_type)
        return {
            "result": "cloud_tasks_error",
            "dispatch_backend": AsyncExecutionMode.CLOUD_TASKS,
            "error": str(exc),
        }


def dispatch_job(
    *,
    job_type: str,
    cloud_task_config: CloudTaskDispatchConfig | None = None,
    local_worker_available: bool = False,
    inline_handler: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    cloud_enabled = cloud_task_config is not None and cloud_tasks_ready(cloud_task_config)
    requested_backend = get_async_execution_mode(
        job_type,
        cloud_tasks_enabled=bool(cloud_enabled),
        local_worker_available=local_worker_available,
    )

    if requested_backend == AsyncExecutionMode.LOCAL_WORKER:
        return {"result": "local_worker_pending", "dispatch_backend": AsyncExecutionMode.LOCAL_WORKER}

    if requested_backend == AsyncExecutionMode.SYNC_INLINE_FOR_TESTS:
        return _dispatch_inline(inline_handler=inline_handler, requested_backend=requested_backend)

    if requested_backend == AsyncExecutionMode.DISABLED:
        return {"result": "pipeline_unavailable", "dispatch_backend": AsyncExecutionMode.DISABLED}

    enqueue_result = _enqueue_cloud_task(
        cloud_task_config
        or CloudTaskDispatchConfig(
            job_type=job_type,
            enabled=False,
            queue="",
            location="",
            handler_url="",
            payload={},
        )
    )
    if enqueue_result["result"] in {"enqueued", "already_enqueued"}:
        enqueue_result.setdefault("requested_backend", requested_backend)
        return enqueue_result

    fallback_mode = get_async_execution_fallback_mode(
        job_type,
        local_worker_available=local_worker_available,
    )
    fallback_reason = str(enqueue_result.get("result") or "")

    if fallback_mode == AsyncExecutionMode.LOCAL_WORKER:
        return {
            "result": "local_worker_pending",
            "dispatch_backend": AsyncExecutionMode.LOCAL_WORKER,
            "requested_backend": requested_backend,
            "fallback_reason": fallback_reason,
        }

    if fallback_mode == AsyncExecutionMode.SYNC_INLINE_FOR_TESTS:
        return _dispatch_inline(
            inline_handler=inline_handler,
            requested_backend=requested_backend,
            fallback_reason=fallback_reason,
        )

    return {
        "result": "pipeline_unavailable",
        "dispatch_backend": AsyncExecutionMode.DISABLED,
        "requested_backend": requested_backend,
        "fallback_reason": fallback_reason,
        "error": str(enqueue_result.get("error") or ""),
    }
