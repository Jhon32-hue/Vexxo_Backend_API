from __future__ import annotations

import logging

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from finance.transactions.Models import TransactionInferenceRequest
from finance.transactions.transaction_inference_dispatch_service import dispatch_transaction_inference
from integrations_stub.llm.services import process_stub_transaction_inference_request

logger = logging.getLogger(__name__)


def _local_worker_batch_size() -> int:
    return max(1, int(getattr(settings, "TRANSACTION_INFERENCE_LOCAL_WORKER_BATCH_SIZE", 25) or 25))


def _local_worker_stale_after_seconds() -> int:
    return max(30, int(getattr(settings, "TRANSACTION_INFERENCE_LOCAL_WORKER_STALE_AFTER_SECONDS", 900) or 900))


def _queued_dispatch_stale_after_seconds() -> int:
    return max(30, int(getattr(settings, "TRANSACTION_INFERENCE_DISPATCH_STALE_AFTER_SECONDS", 120) or 120))


def _processing_stale_after_seconds() -> int:
    return max(60, int(getattr(settings, "TRANSACTION_INFERENCE_PROCESSING_STALE_AFTER_SECONDS", 900) or 900))


def _max_stale_recoveries() -> int:
    return max(1, int(getattr(settings, "TRANSACTION_INFERENCE_MAX_STALE_RECOVERIES", 3) or 3))


def _local_backend_scope():
    return models.Q(dispatch_backend="") | models.Q(
        dispatch_backend=TransactionInferenceRequest.DispatchBackend.LOCAL_WORKER
    )


def redispatch_stale_queued_inference_requests(*, source: str = "transactions.inference.recovery", limit: int | None = None) -> dict:
    now = timezone.now()
    stale_threshold = now - timezone.timedelta(seconds=_queued_dispatch_stale_after_seconds())
    batch_size = int(limit or _local_worker_batch_size())
    requests = list(
        TransactionInferenceRequest.objects.filter(
            status=TransactionInferenceRequest.Status.QUEUED,
            processing_started_at__isnull=True,
            requested_at__lte=stale_threshold,
        )
        .filter(models.Q(last_dispatch_attempt_at__isnull=True) | models.Q(last_dispatch_attempt_at__lte=stale_threshold))
        .order_by("requested_at")[:batch_size]
    )
    redispatched = 0
    for inference_request in requests:
        result = dispatch_transaction_inference(
            inference_request_id=inference_request.pk,
            request_id=inference_request.request_id,
            source=source,
        )
        if result.get("result") in {
            "enqueued",
            "already_enqueued",
            "local_worker_pending",
        }:
            redispatched += 1
    return {
        "scanned": len(requests),
        "redispatched": redispatched,
    }


def recover_stale_processing_inference_requests(*, source: str = "transactions.inference.stale_recovery", limit: int | None = None) -> dict:
    now = timezone.now()
    stale_threshold = now - timezone.timedelta(seconds=_processing_stale_after_seconds())
    batch_size = int(limit or _local_worker_batch_size())
    requests = list(
        TransactionInferenceRequest.objects.filter(
            status=TransactionInferenceRequest.Status.PROCESSING,
            processing_started_at__lte=stale_threshold,
        )
        .filter(_local_backend_scope())
        .order_by("processing_started_at")[:batch_size]
    )
    recovered = 0
    dead_lettered = 0
    redispatched = 0
    for inference_request in requests:
        with transaction.atomic():
            inference_request = TransactionInferenceRequest.objects.select_for_update().get(pk=inference_request.pk)
            if inference_request.status != TransactionInferenceRequest.Status.PROCESSING:
                continue
            reason = "El worker local durable detecto una solicitud de voz atascada y la recupero."
            if int(inference_request.stale_recovery_count or 0) + 1 >= _max_stale_recoveries():
                inference_request.mark_dead_letter(reason=reason)
                dead_lettered += 1
                continue
            inference_request.mark_processing_stale(reason=reason)
            recovered += 1
        result = dispatch_transaction_inference(
            inference_request_id=inference_request.pk,
            request_id=inference_request.request_id,
            source=source,
        )
        if result.get("result") in {
            "enqueued",
            "already_enqueued",
            "local_worker_pending",
        }:
            redispatched += 1
    return {
        "scanned": len(requests),
        "recovered": recovered,
        "dead_lettered": dead_lettered,
        "redispatched": redispatched,
    }


def claim_local_worker_requests(*, worker_id: str, limit: int | None = None) -> list[TransactionInferenceRequest]:
    now = timezone.now()
    batch_size = int(limit or _local_worker_batch_size())
    candidates = list(
        TransactionInferenceRequest.objects.filter(
            status__in=[
                TransactionInferenceRequest.Status.QUEUED,
                TransactionInferenceRequest.Status.DISPATCH_FAILED,
                TransactionInferenceRequest.Status.PROCESSING_STALE,
            ]
        )
        .filter(_local_backend_scope())
        .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now))
        .order_by("requested_at")[: batch_size * 3]
    )
    claimed: list[TransactionInferenceRequest] = []
    for inference_request in candidates:
        if inference_request.claim_for_local_worker(
            worker_id=worker_id,
            stale_after_seconds=_local_worker_stale_after_seconds(),
        ):
            claimed.append(inference_request)
        if len(claimed) >= batch_size:
            break
    return claimed


def process_local_worker_requests(*, worker_id: str, limit: int | None = None, source: str = "transactions.inference.local_worker") -> dict:
    claimed_requests = claim_local_worker_requests(worker_id=worker_id, limit=limit)
    processed = 0
    skipped = 0
    failed = 0
    results: list[dict] = []
    for inference_request in claimed_requests:
        try:
            result = process_stub_transaction_inference_request(
                inference_request_id=inference_request.pk,
                request_id=inference_request.request_id,
                source=source,
            )
        except Exception as exc:
            logger.exception(
                "[transactions.inference.worker] exception processing inference_request_id=%s",
                inference_request.pk,
            )
            with transaction.atomic():
                current = TransactionInferenceRequest.objects.select_for_update().get(pk=inference_request.pk)
                reason = f"local_worker_exception:{exc}"
                if current.status == TransactionInferenceRequest.Status.PROCESSING:
                    if int(current.stale_recovery_count or 0) + 1 >= _max_stale_recoveries():
                        current.mark_dead_letter(reason=reason)
                    else:
                        current.mark_processing_stale(reason=reason)
                else:
                    current.mark_dispatch_failed(
                        error=reason,
                        backend=TransactionInferenceRequest.DispatchBackend.LOCAL_WORKER,
                    )
            result = {"result": "worker_exception", "status": ""}
        results.append(
            {
                "inference_request_id": str(inference_request.pk),
                "result": result.get("result", ""),
                "status": result.get("status", ""),
            }
        )
        if result.get("result") == "processed":
            processed += 1
        elif result.get("result") == "skipped":
            skipped += 1
        else:
            failed += 1
    return {
        "claimed": len(claimed_requests),
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


def run_local_worker_cycle(*, worker_id: str, limit: int | None = None) -> dict:
    stale_dispatch = redispatch_stale_queued_inference_requests(
        source="transactions.inference.local_worker.redispatch",
        limit=limit,
    )
    stale_processing = recover_stale_processing_inference_requests(
        source="transactions.inference.local_worker.recover",
        limit=limit,
    )
    processing = process_local_worker_requests(
        worker_id=worker_id,
        limit=limit,
        source="transactions.inference.local_worker",
    )
    summary = {
        "redispatch_stale_queued": stale_dispatch,
        "recover_stale_processing": stale_processing,
        "process": processing,
    }
    logger.info("[transactions.inference.worker] cycle=%s", summary)
    return summary
