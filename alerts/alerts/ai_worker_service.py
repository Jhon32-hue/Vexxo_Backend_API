from __future__ import annotations

import logging

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from alerts.alerts.ai_services import enrich_alert_with_ai
from alerts.alerts.models import Alert, AlertAiDispatchState

logger = logging.getLogger(__name__)


def _local_worker_batch_size() -> int:
    return max(1, int(getattr(settings, "ALERTS_AI_LOCAL_WORKER_BATCH_SIZE", 25) or 25))


def _local_worker_stale_after_seconds() -> int:
    return max(30, int(getattr(settings, "ALERTS_AI_LOCAL_WORKER_STALE_AFTER_SECONDS", 900) or 900))


def _queued_dispatch_stale_after_seconds() -> int:
    return max(30, int(getattr(settings, "ALERTS_AI_DISPATCH_STALE_AFTER_SECONDS", 120) or 120))


def _processing_stale_after_seconds() -> int:
    return max(60, int(getattr(settings, "ALERTS_AI_PROCESSING_STALE_AFTER_SECONDS", 900) or 900))


def _max_stale_recoveries() -> int:
    return max(1, int(getattr(settings, "ALERTS_AI_MAX_STALE_RECOVERIES", 3) or 3))


def _max_retries() -> int:
    return max(1, int(getattr(settings, "ALERTS_AI_MAX_RETRIES", 3) or 3))


def get_or_create_alert_ai_state(*, alert_id, status: str = AlertAiDispatchState.Status.QUEUED) -> AlertAiDispatchState | None:
    alert = Alert.objects.filter(pk=alert_id).first()
    if alert is None:
        return None
    state, created = AlertAiDispatchState.objects.get_or_create(
        alert=alert,
        defaults={"status": status},
    )
    return state


def request_alert_ai_enrichment(*, alert_id, force: bool = False) -> dict:
    state = get_or_create_alert_ai_state(alert_id=alert_id)
    if state is None:
        return {"result": "missing_alert", "should_dispatch": False}

    now = timezone.now()
    state.request_count = int(state.request_count or 0) + 1
    should_dispatch = bool(
        force
        or state.status in state.processable_statuses
        or state.status == AlertAiDispatchState.Status.FAILED
    )
    if should_dispatch:
        state.mark_queued(commit=False)
    state.save()
    return {"result": "queued" if should_dispatch else "coalesced", "should_dispatch": should_dispatch, "state_id": state.pk}


def process_alert_ai_request(*, alert_id, correlation_id: str = "", source: str = "") -> dict:
    state = get_or_create_alert_ai_state(alert_id=alert_id)
    if state is None:
        return {"result": "missing_alert"}
    with transaction.atomic():
        state = AlertAiDispatchState.objects.select_for_update().select_related("alert").get(pk=state.pk)
        if state.status not in state.processable_statuses:
            return {"result": "skipped", "status": state.status}
        state.mark_processing()
    try:
        result = enrich_alert_with_ai(
            state.alert,
            correlation_id=correlation_id or None,
            raise_on_error=True,
        )
        state.refresh_from_db()
        state.mark_applied()
        return {"result": "processed", "status": state.status, "llm_result": result, "source": source}
    except Exception as exc:
        logger.exception("[alerts.ai.worker] error alert_id=%s", alert_id)
        state.refresh_from_db()
        state.mark_failed(error=f"alert_ai_exception:{exc}", max_retries=_max_retries())
        return {"result": "failed", "status": state.status, "error": str(exc)}


def redispatch_stale_queued_alert_ai(*, dispatch_fn, limit: int | None = None) -> dict:
    now = timezone.now()
    stale_threshold = now - timezone.timedelta(seconds=_queued_dispatch_stale_after_seconds())
    batch_size = int(limit or _local_worker_batch_size())
    states = list(
        AlertAiDispatchState.objects.filter(
            status=AlertAiDispatchState.Status.QUEUED,
            processing_started_at__isnull=True,
            requested_at__lte=stale_threshold,
        )
        .filter(models.Q(last_dispatch_attempt_at__isnull=True) | models.Q(last_dispatch_attempt_at__lte=stale_threshold))
        .order_by("requested_at")[:batch_size]
    )
    redispatched = 0
    for state in states:
        result = dispatch_fn(alert_id=state.alert_id, force=True, source="alerts.ai.local_worker.redispatch")
        if result.get("result") in {"enqueued", "already_enqueued", "local_worker_pending"}:
            redispatched += 1
    return {"scanned": len(states), "redispatched": redispatched}


def recover_stale_processing_alert_ai(*, dispatch_fn, limit: int | None = None) -> dict:
    now = timezone.now()
    stale_threshold = now - timezone.timedelta(seconds=_processing_stale_after_seconds())
    batch_size = int(limit or _local_worker_batch_size())
    states = list(
        AlertAiDispatchState.objects.filter(
            status=AlertAiDispatchState.Status.PROCESSING,
            processing_started_at__lte=stale_threshold,
        ).order_by("processing_started_at")[:batch_size]
    )
    recovered = 0
    dead_lettered = 0
    redispatched = 0
    for state in states:
        with transaction.atomic():
            state = AlertAiDispatchState.objects.select_for_update().get(pk=state.pk)
            if state.status != AlertAiDispatchState.Status.PROCESSING:
                continue
            reason = "El worker local durable detecto una alerta atascada y la recupero."
            if int(state.stale_recovery_count or 0) + 1 >= _max_stale_recoveries():
                state.status = AlertAiDispatchState.Status.DEAD_LETTER
                state.failed_at = now
                state.last_error = reason
                state.last_operational_issue = "dead_letter"
                state.local_worker_locked_at = None
                state.local_worker_locked_by = ""
                state.next_attempt_at = None
                state.save()
                dead_lettered += 1
                continue
            state.mark_processing_stale(reason=reason)
            recovered += 1
        result = dispatch_fn(alert_id=state.alert_id, force=True, source="alerts.ai.local_worker.recover")
        if result.get("result") in {"enqueued", "already_enqueued", "local_worker_pending"}:
            redispatched += 1
    return {
        "scanned": len(states),
        "recovered": recovered,
        "dead_lettered": dead_lettered,
        "redispatched": redispatched,
    }


def claim_local_worker_states(*, worker_id: str, limit: int | None = None) -> list[AlertAiDispatchState]:
    now = timezone.now()
    batch_size = int(limit or _local_worker_batch_size())
    candidates = list(
        AlertAiDispatchState.objects.select_related("alert")
        .filter(
            status__in=[
                AlertAiDispatchState.Status.QUEUED,
                AlertAiDispatchState.Status.DISPATCH_FAILED,
                AlertAiDispatchState.Status.PROCESSING_STALE,
            ]
        )
        .filter(
            models.Q(dispatch_backend="")
            | models.Q(dispatch_backend=AlertAiDispatchState.DispatchBackend.LOCAL_WORKER)
        )
        .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now))
        .order_by("requested_at")[: batch_size * 3]
    )
    claimed: list[AlertAiDispatchState] = []
    for state in candidates:
        if state.claim_for_local_worker(worker_id=worker_id, stale_after_seconds=_local_worker_stale_after_seconds()):
            claimed.append(state)
        if len(claimed) >= batch_size:
            break
    return claimed


def process_local_worker_states(*, worker_id: str, limit: int | None = None) -> dict:
    claimed_states = claim_local_worker_states(worker_id=worker_id, limit=limit)
    processed = 0
    skipped = 0
    failed = 0
    results: list[dict] = []
    for state in claimed_states:
        result = process_alert_ai_request(
            alert_id=state.alert_id,
            correlation_id=state.alert.correlation_id or "",
            source="alerts.ai.local_worker",
        )
        results.append({"alert_id": str(state.alert_id), "result": result.get("result", ""), "status": result.get("status", "")})
        if result.get("result") == "processed":
            processed += 1
        elif result.get("result") == "skipped":
            skipped += 1
        else:
            failed += 1
    return {
        "claimed": len(claimed_states),
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


def run_local_worker_cycle(*, worker_id: str, dispatch_fn, limit: int | None = None) -> dict:
    stale_dispatch = redispatch_stale_queued_alert_ai(dispatch_fn=dispatch_fn, limit=limit)
    stale_processing = recover_stale_processing_alert_ai(dispatch_fn=dispatch_fn, limit=limit)
    processing = process_local_worker_states(worker_id=worker_id, limit=limit)
    summary = {
        "redispatch_stale_queued": stale_dispatch,
        "recover_stale_processing": stale_processing,
        "process": processing,
    }
    logger.info("[alerts.ai.worker] cycle=%s", summary)
    return summary
