from __future__ import annotations

import logging

from django.conf import settings

from tasks.async_backends import (
    AsyncExecutionMode,
    CloudTaskDispatchConfig,
    cloud_tasks_ready,
    dispatch_job,
    get_async_execution_fallback_mode,
    get_async_execution_mode,
)

logger = logging.getLogger(__name__)

JOB_TYPE = "transactions.voice"


def transaction_inference_cloud_tasks_ready() -> bool:
    return cloud_tasks_ready(_cloud_task_config(inference_request_id="", request_id="", source=""))


def transaction_inference_execution_mode() -> str:
    return get_async_execution_mode(
        JOB_TYPE,
        cloud_tasks_enabled=transaction_inference_cloud_tasks_ready(),
    )


def transaction_inference_fallback_mode() -> str:
    return get_async_execution_fallback_mode(
        JOB_TYPE,
    )


def _update_dispatch_metrics(*, inference_request_id, backend: str = "", result: str = "", error: str = "") -> None:
    from finance.transactions.Models import TransactionInferenceRequest

    inference_request = TransactionInferenceRequest.objects.filter(pk=inference_request_id).first()
    if inference_request is None:
        return
    inference_request.note_dispatch_attempt(backend=backend, result=result, error=error)


def _mark_dispatch_failed(*, inference_request_id, backend: str = "", error: str = "") -> None:
    from finance.transactions.Models import TransactionInferenceRequest

    inference_request = TransactionInferenceRequest.objects.filter(pk=inference_request_id).first()
    if inference_request is None:
        return
    inference_request.note_dispatch_attempt(backend=backend, result="dispatch_failed", error=error)
    inference_request.mark_dispatch_failed(error=error or "No fue posible despachar la solicitud de voz.", backend=backend)


def _schedule_local_worker_pickup(*, inference_request_id, request_id: str = "", source: str = "") -> dict:
    del request_id, source
    _update_dispatch_metrics(
        inference_request_id=inference_request_id,
        backend="local_worker",
        result="local_worker_pending",
    )
    return {
        "result": "local_worker_pending",
        "dispatch_backend": "local_worker",
        "inference_request_id": str(inference_request_id),
    }


def _cloud_task_config(*, inference_request_id, request_id: str = "", source: str = "") -> CloudTaskDispatchConfig:
    return CloudTaskDispatchConfig(
        job_type=JOB_TYPE,
        enabled=bool(getattr(settings, "TRANSACTION_INFERENCE_CLOUD_TASKS_ENABLED", False)),
        queue=str(getattr(settings, "TRANSACTION_INFERENCE_CLOUD_TASKS_QUEUE", "") or ""),
        location=str(getattr(settings, "TRANSACTION_INFERENCE_CLOUD_TASKS_LOCATION", "") or ""),
        handler_url=str(getattr(settings, "TRANSACTION_INFERENCE_HANDLER_URL", "") or ""),
        payload={
            "inference_request_id": str(inference_request_id or ""),
            "request_id": str(request_id or ""),
            "source": str(source or "finance.transactions.transaction_inference_dispatch_service"),
        },
        task_name=f"tx-inference-{inference_request_id}" if inference_request_id else "",
        internal_token=str(getattr(settings, "TRANSACTION_INFERENCE_INTERNAL_TOKEN", "") or ""),
        service_account_email=str(getattr(settings, "TRANSACTION_INFERENCE_TASK_SERVICE_ACCOUNT_EMAIL", "") or ""),
        audience=str(getattr(settings, "TRANSACTION_INFERENCE_TASK_AUDIENCE", "") or ""),
        buffer_seconds=max(0, int(getattr(settings, "TRANSACTION_INFERENCE_TASK_BUFFER_SECONDS", 5) or 5)),
    )


def _process_inline_for_tests(*, inference_request_id, request_id: str = "", source: str = "") -> dict:
    from integrations_stub.llm.services import process_stub_transaction_inference_request

    return process_stub_transaction_inference_request(
        inference_request_id=inference_request_id,
        request_id=request_id,
        source=source or "transactions.voice.inline",
    )


def dispatch_transaction_inference(*, inference_request_id, request_id: str = "", source: str = "") -> dict:
    if not inference_request_id:
        return {"result": "missing_inference_request_id"}

    dispatch_result = dispatch_job(
        job_type=JOB_TYPE,
        cloud_task_config=_cloud_task_config(
            inference_request_id=inference_request_id,
            request_id=request_id,
            source=source,
        ),
        inline_handler=lambda: _process_inline_for_tests(
            inference_request_id=inference_request_id,
            request_id=request_id,
            source=source,
        ),
    )
    result = str(dispatch_result.get("result") or "")
    backend = str(dispatch_result.get("dispatch_backend") or "")

    if result in {"enqueued", "already_enqueued"}:
        _update_dispatch_metrics(
            inference_request_id=inference_request_id,
            backend=AsyncExecutionMode.CLOUD_TASKS,
            result=result,
        )
        return dispatch_result

    if result == "local_worker_pending":
        return _schedule_local_worker_pickup(
            inference_request_id=inference_request_id,
            request_id=request_id,
            source=source,
        )

    if result == "inline_processed":
        _update_dispatch_metrics(
            inference_request_id=inference_request_id,
            backend=AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
            result=result,
        )
        return dispatch_result

    if result == "inline_handler_failed":
        _mark_dispatch_failed(
            inference_request_id=inference_request_id,
            backend=AsyncExecutionMode.SYNC_INLINE_FOR_TESTS,
            error=f"inline_handler_failed:{dispatch_result.get('error', '')}",
        )
        return {"result": "pipeline_unavailable", "dispatch_backend": backend or AsyncExecutionMode.SYNC_INLINE_FOR_TESTS}

    if result == "pipeline_unavailable":
        _mark_dispatch_failed(
            inference_request_id=inference_request_id,
            backend=backend,
            error=f"pipeline_unavailable:{dispatch_result.get('fallback_reason') or dispatch_result.get('error') or result}",
        )
        return {"result": "pipeline_unavailable", "dispatch_backend": backend}

    _mark_dispatch_failed(
        inference_request_id=inference_request_id,
        backend=backend or AsyncExecutionMode.CLOUD_TASKS,
        error=f"{result}:{dispatch_result.get('error', '')}",
    )
    return {"result": "pipeline_unavailable", "dispatch_backend": backend or AsyncExecutionMode.CLOUD_TASKS}
