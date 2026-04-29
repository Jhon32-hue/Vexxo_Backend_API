from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def transaction_inference_cloud_tasks_ready() -> bool:
    return bool(
        getattr(settings, "TRANSACTION_INFERENCE_CLOUD_TASKS_ENABLED", False)
        and getattr(settings, "GCP_PROJECT_ID", "")
        and getattr(settings, "TRANSACTION_INFERENCE_CLOUD_TASKS_QUEUE", "")
        and getattr(settings, "TRANSACTION_INFERENCE_HANDLER_URL", "")
    )


def transaction_inference_local_fallback_allowed() -> bool:
    env_value = str(getattr(settings, "ENV", "local")).strip().lower()
    if env_value in {"prod", "production", "cloud"} and not bool(getattr(settings, "DEBUG", False)):
        return False
    return bool(getattr(settings, "TRANSACTION_INFERENCE_LOCAL_FALLBACK_ENABLED", True))


def _scheduled_time() -> datetime:
    return datetime.now(dt_timezone.utc) + timedelta(
        seconds=max(0, int(getattr(settings, "TRANSACTION_INFERENCE_TASK_BUFFER_SECONDS", 5)))
    )


def _run_local_fallback(*, inference_request_id, request_id: str = "", source: str = "") -> None:
    try:
        close_old_connections()
        from integrations_stub.llm.services import process_stub_transaction_inference_request

        process_stub_transaction_inference_request(
            inference_request_id=inference_request_id,
            request_id=request_id,
            source=source,
        )
    except Exception:
        logger.exception(
            "[transactions.inference] Fallback local async fallo para inference_request_id=%s",
            inference_request_id,
        )
    finally:
        close_old_connections()


def _dispatch_local_fallback_async(*, inference_request_id, request_id: str = "", source: str = "") -> dict:
    worker = threading.Thread(
        target=_run_local_fallback,
        kwargs={
            "inference_request_id": inference_request_id,
            "request_id": request_id,
            "source": source,
        },
        name=f"tx-inference-local-{inference_request_id}",
        daemon=True,
    )
    worker.start()
    return {
        "result": "local_fallback_enqueued",
        "mode": "background_thread",
        "inference_request_id": str(inference_request_id),
    }


def enqueue_transaction_inference_task(*, inference_request_id, request_id: str = "", source: str = "") -> dict:
    if not inference_request_id or not transaction_inference_cloud_tasks_ready():
        return {"result": "cloud_tasks_unavailable"}

    try:
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
    except Exception:
        logger.warning("[transactions.inference] Cloud Tasks configurado, pero falta `google-cloud-tasks`.")
        return {"result": "cloud_tasks_client_unavailable"}

    try:
        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(
            settings.GCP_PROJECT_ID,
            settings.TRANSACTION_INFERENCE_CLOUD_TASKS_LOCATION,
            settings.TRANSACTION_INFERENCE_CLOUD_TASKS_QUEUE,
        )
        body = json.dumps(
            {
                "inference_request_id": str(inference_request_id),
                "request_id": str(request_id or ""),
                "source": str(source or "finance.transactions.transaction_inference_dispatch_service"),
            },
            default=str,
        ).encode("utf-8")
        handler_url = settings.TRANSACTION_INFERENCE_HANDLER_URL
        http_request = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": handler_url,
            "headers": {
                "Content-Type": "application/json",
                "X-Vexxo-Internal-Token": str(getattr(settings, "TRANSACTION_INFERENCE_INTERNAL_TOKEN", "") or ""),
            },
            "body": body,
        }
        if getattr(settings, "TRANSACTION_INFERENCE_TASK_SERVICE_ACCOUNT_EMAIL", ""):
            http_request["oidc_token"] = {
                "service_account_email": settings.TRANSACTION_INFERENCE_TASK_SERVICE_ACCOUNT_EMAIL,
                "audience": getattr(settings, "TRANSACTION_INFERENCE_TASK_AUDIENCE", "") or handler_url,
            }

        task = {"http_request": http_request}
        ts = timestamp_pb2.Timestamp()
        ts.FromDatetime(_scheduled_time())
        task["schedule_time"] = ts
        task["name"] = f"{parent}/tasks/tx-inference-{inference_request_id}"
        response = client.create_task(request={"parent": parent, "task": task})
        return {"result": "enqueued", "task_name": getattr(response, "name", task["name"])}
    except AlreadyExists:
        logger.info("[transactions.inference] Task ya existente para inference_request_id=%s", inference_request_id)
        return {"result": "already_enqueued", "task_name": task["name"]}
    except Exception:
        logger.exception(
            "[transactions.inference] Error creando Cloud Task para inference_request_id=%s",
            inference_request_id,
        )
        return {"result": "cloud_tasks_error"}


def dispatch_transaction_inference(*, inference_request_id, request_id: str = "", source: str = "") -> dict:
    if not inference_request_id:
        return {"result": "missing_inference_request_id"}

    enqueue_result = enqueue_transaction_inference_task(
        inference_request_id=inference_request_id,
        request_id=request_id,
        source=source,
    )
    if enqueue_result["result"] in {"enqueued", "already_enqueued"}:
        return enqueue_result

    if not transaction_inference_local_fallback_allowed():
        return {"result": "pipeline_unavailable", "dispatch_backend": enqueue_result["result"]}

    return _dispatch_local_fallback_async(
        inference_request_id=inference_request_id,
        request_id=request_id,
        source=source,
    )
