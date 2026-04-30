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

import logging

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from tasks.async_backends import (
    AsyncExecutionMode,
    CloudTaskDispatchConfig,
    cloud_tasks_ready,
    dispatch_job,
    get_async_execution_fallback_mode,
    get_async_execution_mode,
)

logger = logging.getLogger(__name__)
JOB_TYPE = "accounts.intelligence"


def intelligence_cloud_tasks_ready() -> bool:
    return cloud_tasks_ready(_cloud_task_config(event=None, owner_id="", task_name_suffix=None, source=""))

def account_intelligence_execution_mode() -> str:
    return get_async_execution_mode(
        JOB_TYPE,
        cloud_tasks_enabled=intelligence_cloud_tasks_ready(),
    )


def account_intelligence_fallback_mode() -> str:
    return get_async_execution_fallback_mode(
        JOB_TYPE,
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
        was_pending = bool(state.pending_request)

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

        state.pending_request = True if should_dispatch else was_pending
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
        last_operational_issue="",
        next_attempt_at=None,
    )


def _update_dispatch_metrics(*, owner_id: str | int | None, backend: str = "", result: str = "", error_message: str = "") -> None:
    if not owner_id:
        return

    from finance.accounts.models import AccountIntelligenceDispatchState

    AccountIntelligenceDispatchState.objects.filter(owner_id=owner_id).update(
        dispatch_backend=(backend or "")[:32],
        dispatch_attempt_count=models.F("dispatch_attempt_count") + 1,
        last_dispatch_attempt_at=timezone.now(),
        last_dispatch_error=str(error_message or "")[:2000],
        last_result=(result or "")[:64],
    )


def _mark_local_worker_pending(*, owner_id: str | int | None) -> None:
    from finance.accounts.models import AccountIntelligenceDispatchState

    if not owner_id:
        return
    _update_dispatch_metrics(
        owner_id=owner_id,
        backend=AccountIntelligenceDispatchState.DispatchBackend.LOCAL_WORKER,
        result="local_worker_pending",
    )
    AccountIntelligenceDispatchState.objects.filter(owner_id=owner_id).update(
        pending_request=True,
        last_enqueued_at=timezone.now(),
        last_task_name="",
        last_result="local_worker_pending",
        last_error_message="",
        last_operational_issue="",
        next_attempt_at=None,
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
        state.last_operational_issue = ""
        state.next_attempt_at = None
        state.local_worker_locked_at = None
        state.local_worker_locked_by = ""
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
        last_operational_issue="",
        next_attempt_at=None,
        local_worker_locked_at=None,
        local_worker_locked_by="",
    )


def mark_account_intelligence_refresh_blocked(*, owner_id: str | int | None, result: str = "blocked") -> None:
    from finance.accounts.models import AccountIntelligenceDispatchState

    if not owner_id:
        return
    AccountIntelligenceDispatchState.objects.filter(owner_id=owner_id).update(
        pending_request=True,
        last_result=(result or "blocked")[:64],
        last_operational_issue="pipeline_unavailable",
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
        state.last_operational_issue = "worker_failed"
        state.local_worker_locked_at = None
        state.local_worker_locked_by = ""
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
        state.last_operational_issue = ""
        state.next_attempt_at = None
        state.local_worker_locked_at = None
        state.local_worker_locked_by = ""
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

    dispatch_result = dispatch_job(
        job_type=JOB_TYPE,
        cloud_task_config=_cloud_task_config(
            event=event,
            owner_id=owner_id,
            task_name_suffix=task_name_suffix,
            source=source,
        ),
        inline_handler=lambda: _process_inline_for_tests(
            owner_id=owner_id,
            event=event,
            source=source,
            task_name_suffix=task_name_suffix,
        ),
    )
    result = str(dispatch_result.get("result") or "")

    if result in {"enqueued", "already_enqueued"}:
        _update_dispatch_metrics(owner_id=owner_id, backend=AsyncExecutionMode.CLOUD_TASKS, result=result)
        mark_account_intelligence_refresh_enqueued(
            owner_id=owner_id,
            task_name=str(dispatch_result.get("task_name", "") or ""),
            result=result,
        )
        return {**request, "result": result, "task_name": str(dispatch_result.get("task_name", "") or "")}

    if result == "local_worker_pending":
        _mark_local_worker_pending(owner_id=owner_id)
        return {**request, "result": "local_worker_pending"}

    if result == "inline_processed":
        _update_dispatch_metrics(
            owner_id=owner_id,
            backend=AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
            result=result,
        )
        return {**request, **dispatch_result}

    error_message = str(dispatch_result.get("fallback_reason") or dispatch_result.get("error") or result or "pipeline_unavailable")
    backend = str(dispatch_result.get("dispatch_backend") or "")
    _update_dispatch_metrics(owner_id=owner_id, backend=backend, result="pipeline_unavailable", error_message=error_message)
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
        "async_execution_mode": account_intelligence_execution_mode(),
        "async_execution_fallback_mode": account_intelligence_fallback_mode(),
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
        "dispatch_backend": str(getattr(dispatch_state, "dispatch_backend", "") or ""),
        "dispatch_attempt_count": int(getattr(dispatch_state, "dispatch_attempt_count", 0) or 0),
        "dispatch_last_attempt_at": dispatch_state.last_dispatch_attempt_at.isoformat() if getattr(dispatch_state, "last_dispatch_attempt_at", None) else None,
        "dispatch_last_attempt_error": str(getattr(dispatch_state, "last_dispatch_error", "") or ""),
        "dispatch_local_worker_locked_at": dispatch_state.local_worker_locked_at.isoformat() if getattr(dispatch_state, "local_worker_locked_at", None) else None,
        "dispatch_local_worker_locked_by": str(getattr(dispatch_state, "local_worker_locked_by", "") or ""),
        "dispatch_stale_recovery_count": int(getattr(dispatch_state, "stale_recovery_count", 0) or 0),
        "dispatch_last_recovered_at": dispatch_state.last_recovered_at.isoformat() if getattr(dispatch_state, "last_recovered_at", None) else None,
        "dispatch_last_operational_issue": str(getattr(dispatch_state, "last_operational_issue", "") or ""),
        "dispatch_next_attempt_at": dispatch_state.next_attempt_at.isoformat() if getattr(dispatch_state, "next_attempt_at", None) else None,
    }


def account_intelligence_local_fallback_allowed() -> bool:
    mode = account_intelligence_execution_mode()
    fallback = account_intelligence_fallback_mode()
    return mode == AsyncExecutionMode.LOCAL_WORKER or fallback == AsyncExecutionMode.LOCAL_WORKER


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


def _cloud_task_config(*, event=None, owner_id: str | int | None, task_name_suffix: str | None = None, source: str = "") -> CloudTaskDispatchConfig:
    safe_suffix = str(task_name_suffix or owner_id or "default").replace("/", "-").replace(":", "-")
    return CloudTaskDispatchConfig(
        job_type=JOB_TYPE,
        enabled=bool(getattr(settings, "ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_ENABLED", False)),
        queue=str(getattr(settings, "ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_QUEUE", "") or ""),
        location=str(getattr(settings, "ACCOUNTS_INTELLIGENCE_CLOUD_TASKS_LOCATION", "") or ""),
        handler_url=str(getattr(settings, "ACCOUNTS_INTELLIGENCE_HANDLER_URL", "") or ""),
        payload={
            "event": _event_as_dict(event),
            "owner_id": str(owner_id or ""),
            "source": source or "accounts.intelligence_dispatch",
        },
        task_name=f"accounts-intelligence-{safe_suffix}" if owner_id else "",
        internal_token=str(getattr(settings, "ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN", "") or ""),
        service_account_email=str(getattr(settings, "ACCOUNTS_INTELLIGENCE_TASK_SERVICE_ACCOUNT_EMAIL", "") or ""),
        audience=str(getattr(settings, "ACCOUNTS_INTELLIGENCE_TASK_AUDIENCE", "") or ""),
        buffer_seconds=max(0, int(getattr(settings, "ACCOUNTS_INTELLIGENCE_TASK_BUFFER_SECONDS", 10) or 10)),
        headers={
            "X-Vexxo-Event-Type": getattr(event, "type", "accounts.intelligence.refresh.requested.v1"),
            "X-Vexxo-Context": getattr(getattr(event, "context", None), "value", "accounts"),
        },
    )


def _process_inline_for_tests(*, owner_id: str | int | None, event=None, source: str = "", task_name_suffix: str | None = None) -> dict:
    from django.contrib.auth import get_user_model

    from finance.accounts.services.intelligence_service import refresh_account_intelligence_for_user

    if not owner_id:
        return {"result": "owner_missing"}

    task_name = f"inline:{task_name_suffix or owner_id}"
    mark_account_intelligence_refresh_started(
        owner_id=owner_id,
        task_name=task_name,
        result="inline_started",
    )
    user = get_user_model().objects.filter(pk=owner_id).first()
    if user is None:
        mark_account_intelligence_refresh_failed(
            owner_id=owner_id,
            task_name=task_name,
            result="inline_failed",
            error_message="owner_missing",
        )
        return {"result": "owner_missing"}
    try:
        refresh_result = refresh_account_intelligence_for_user(user, event=event, source=source or "accounts.intelligence.inline")
        mark_account_intelligence_refresh_completed_for_task(
            owner_id=owner_id,
            task_name=task_name,
            result="inline_completed",
        )
        return {"result": "processed", "refresh_result": refresh_result}
    except Exception as exc:
        logger.exception("[accounts.intelligence] inline handler failed owner_id=%s", owner_id)
        mark_account_intelligence_refresh_failed(
            owner_id=owner_id,
            task_name=task_name,
            result="inline_failed",
            error_message=str(exc),
        )
        raise
