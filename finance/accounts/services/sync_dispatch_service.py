"""
Orquestacion canonica del job async `accounts.sync`.

Descripcion general:
- transforma eventos `accounts.sync.scheduled.v1` en trabajo async usando la
  misma frontera comun que ya usan `accounts.intelligence`, `alerts.ai` y
  `transactions.voice`
- conserva la semantica operativa del sync: schedule_time derivado de
  `next_sync_at`, idempotencia por task name y local worker durable cuando
  corresponde
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings

from finance.accounts.models import Account
from finance.accounts.services.sync_worker_service import (
    accounts_sync_local_worker_enabled,
    mark_account_sync_local_worker_pending,
    mark_account_sync_pipeline_unavailable,
    note_sync_dispatch_attempt,
)
from tasks.async_backends import (
    AsyncExecutionMode,
    CloudTaskDispatchConfig,
    cloud_tasks_ready,
    dispatch_job,
    get_async_execution_fallback_mode,
    get_async_execution_mode,
)

logger = logging.getLogger(__name__)
JOB_TYPE = "accounts.sync"


def _event_as_dict(event) -> dict:
    if event is None:
        return {"type": "accounts.sync.scheduled.v1", "context": "accounts"}
    if hasattr(event, "to_dict"):
        return event.to_dict()
    return {
        "type": getattr(event, "type", "accounts.sync.scheduled.v1"),
        "context": getattr(getattr(event, "context", None), "value", "accounts"),
        "correlation_id": getattr(event, "correlation_id", None),
        "causation_id": getattr(event, "causation_id", None),
    }


def sync_cloud_tasks_ready() -> bool:
    return cloud_tasks_ready(_cloud_task_config(event=None, task_name_suffix=None))


def account_sync_execution_mode() -> str:
    return get_async_execution_mode(
        JOB_TYPE,
        cloud_tasks_enabled=sync_cloud_tasks_ready(),
    )


def account_sync_fallback_mode() -> str:
    return get_async_execution_fallback_mode(
        JOB_TYPE,
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


def _cloud_task_config(*, event=None, task_name_suffix: str | None = None) -> CloudTaskDispatchConfig:
    payload = getattr(event, "payload", None) or {}
    safe_suffix = str(task_name_suffix or payload.get("account_id") or "default").replace("/", "-").replace(":", "-")
    return CloudTaskDispatchConfig(
        job_type=JOB_TYPE,
        enabled=bool(getattr(settings, "ACCOUNTS_SYNC_CLOUD_TASKS_ENABLED", False)),
        queue=str(getattr(settings, "ACCOUNTS_SYNC_CLOUD_TASKS_QUEUE", "") or ""),
        location=str(getattr(settings, "ACCOUNTS_SYNC_CLOUD_TASKS_LOCATION", "") or ""),
        handler_url=str(getattr(settings, "ACCOUNTS_SYNC_HANDLER_URL", "") or ""),
        payload={
            "event": _event_as_dict(event),
            "account_id": str(payload.get("account_id") or ""),
            "provider": str(payload.get("provider") or ""),
            "next_sync_at": payload.get("next_sync_at"),
        },
        task_name=f"accounts-sync-{safe_suffix}" if safe_suffix else "",
        internal_token=str(getattr(settings, "ACCOUNTS_SYNC_INTERNAL_TOKEN", "") or ""),
        service_account_email=str(getattr(settings, "ACCOUNTS_SYNC_TASK_SERVICE_ACCOUNT_EMAIL", "") or ""),
        audience=str(getattr(settings, "ACCOUNTS_SYNC_TASK_AUDIENCE", "") or ""),
        buffer_seconds=max(0, int(getattr(settings, "ACCOUNTS_SYNC_TASK_BUFFER_SECONDS", 0) or 0)),
        scheduled_at=_parse_event_schedule(payload),
        headers={
            "X-Vexxo-Event-Type": getattr(event, "type", "accounts.sync.scheduled.v1"),
            "X-Vexxo-Context": getattr(getattr(event, "context", None), "value", "accounts"),
        },
    )


def _mark_local_worker_pending(*, account_id, result: str = "local_worker_pending") -> dict:
    if account_id:
        mark_account_sync_local_worker_pending(account_id=account_id, result=result)
    return {
        "result": "local_worker_pending",
        "dispatch_backend": AsyncExecutionMode.LOCAL_WORKER,
        "account_id": str(account_id or ""),
    }


def _process_inline_for_tests(*, event=None) -> dict:
    from integrations_stub.banks.services import process_stub_account_sync

    payload = getattr(event, "payload", None) or {}
    account_id = payload.get("account_id")
    account = Account.objects.filter(pk=account_id, external_id__gt="").first()
    if account is None:
        return {"result": "missing_account"}

    process_stub_account_sync(
        account=account,
        event=_event_as_dict(event),
        mode="success",
        next_sync_at=_parse_event_schedule(payload),
        duration_ms=50,
    )
    return {"result": "processed", "account_id": str(account.pk)}


def enqueue_account_sync_task(*, event, task_name_suffix: str | None = None):
    payload = getattr(event, "payload", None) or {}
    account_id = payload.get("account_id")

    dispatch_result = dispatch_job(
        job_type=JOB_TYPE,
        cloud_task_config=_cloud_task_config(
            event=event,
            task_name_suffix=task_name_suffix,
        ),
        inline_handler=lambda: _process_inline_for_tests(event=event),
    )
    result = str(dispatch_result.get("result") or "")
    backend = str(dispatch_result.get("dispatch_backend") or "")

    if result in {"enqueued", "already_enqueued"}:
        if account_id:
            note_sync_dispatch_attempt(
                account_id=account_id,
                backend=AsyncExecutionMode.CLOUD_TASKS,
                result=result,
            )
        return dispatch_result

    if result == "local_worker_pending":
        return _mark_local_worker_pending(account_id=account_id, result="local_worker_pending")

    if result == "inline_processed":
        if account_id:
            note_sync_dispatch_attempt(
                account_id=account_id,
                backend=AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
                result=result,
            )
        return dispatch_result

    error_message = str(dispatch_result.get("fallback_reason") or dispatch_result.get("error") or result or "pipeline_unavailable")
    if account_id:
        mark_account_sync_pipeline_unavailable(account_id=account_id, error=error_message)
    return {"result": "pipeline_unavailable", "dispatch_backend": backend or AsyncExecutionMode.DISABLED}
