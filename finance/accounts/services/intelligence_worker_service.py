from __future__ import annotations

import logging

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from finance.accounts.models import AccountIntelligenceDispatchState
from finance.accounts.services.intelligence_dispatch_service import (
    _mark_local_worker_pending,
    _update_dispatch_metrics,
    mark_account_intelligence_refresh_completed_for_task,
    mark_account_intelligence_refresh_started,
)
from integrations_stub.banks.services import process_stub_account_intelligence_refresh

logger = logging.getLogger(__name__)


def _local_worker_batch_size() -> int:
    return max(1, int(getattr(settings, "ACCOUNTS_INTELLIGENCE_LOCAL_WORKER_BATCH_SIZE", 25) or 25))


def _local_worker_stale_after_seconds() -> int:
    return max(30, int(getattr(settings, "ACCOUNTS_INTELLIGENCE_LOCAL_WORKER_STALE_AFTER_SECONDS", 900) or 900))


def _processing_stale_after_seconds() -> int:
    return max(60, int(getattr(settings, "ACCOUNTS_INTELLIGENCE_PROCESSING_STALE_AFTER_SECONDS", 900) or 900))


def _max_stale_recoveries() -> int:
    return max(1, int(getattr(settings, "ACCOUNTS_INTELLIGENCE_MAX_STALE_RECOVERIES", 3) or 3))


def recover_stale_processing_intelligence_requests(*, limit: int | None = None) -> dict:
    now = timezone.now()
    stale_threshold = now - timezone.timedelta(seconds=_processing_stale_after_seconds())
    batch_size = int(limit or _local_worker_batch_size())
    states = list(
        AccountIntelligenceDispatchState.objects.filter(
            pending_request=True,
            dispatch_backend=AccountIntelligenceDispatchState.DispatchBackend.LOCAL_WORKER,
            last_started_at__isnull=False,
            last_started_at__lte=stale_threshold,
        ).order_by("last_started_at")[:batch_size]
    )
    recovered = 0
    dead_lettered = 0
    for state in states:
        with transaction.atomic():
            state = AccountIntelligenceDispatchState.objects.select_for_update().get(pk=state.pk)
            if not state.pending_request:
                continue
            if int(state.stale_recovery_count or 0) + 1 >= _max_stale_recoveries():
                state.pending_request = False
                state.last_failed_at = now
                state.last_result = "dead_letter"
                state.last_error_message = "accounts.intelligence local worker stale recovery exhausted"
                state.last_operational_issue = "dead_letter"
                state.local_worker_locked_at = None
                state.local_worker_locked_by = ""
                state.next_attempt_at = None
                state.save()
                dead_lettered += 1
                continue
            state.stale_recovery_count = int(state.stale_recovery_count or 0) + 1
            state.last_recovered_at = now
            state.last_failed_at = now
            state.last_result = "processing_stale"
            state.last_error_message = "accounts.intelligence local worker stale processing recovered"
            state.last_operational_issue = "processing_stale"
            state.local_worker_locked_at = None
            state.local_worker_locked_by = ""
            state.last_started_at = None
            state.next_attempt_at = None
            state.save()
            recovered += 1
    return {"scanned": len(states), "recovered": recovered, "dead_lettered": dead_lettered}


def claim_local_worker_requests(*, worker_id: str, limit: int | None = None) -> list[AccountIntelligenceDispatchState]:
    now = timezone.now()
    stale_threshold = now - timezone.timedelta(seconds=_local_worker_stale_after_seconds())
    batch_size = int(limit or _local_worker_batch_size())
    candidates = list(
        AccountIntelligenceDispatchState.objects.filter(
            pending_request=True,
        )
        .filter(
            models.Q(dispatch_backend="") | models.Q(dispatch_backend=AccountIntelligenceDispatchState.DispatchBackend.LOCAL_WORKER)
        )
        .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now))
        .order_by("last_requested_at")[: batch_size * 3]
    )
    claimed: list[AccountIntelligenceDispatchState] = []
    for state in candidates:
        with transaction.atomic():
            updated = (
                AccountIntelligenceDispatchState.objects.filter(pk=state.pk, pending_request=True)
                .filter(models.Q(next_attempt_at__isnull=True) | models.Q(next_attempt_at__lte=now))
                .filter(
                    models.Q(local_worker_locked_at__isnull=True)
                    | models.Q(local_worker_locked_at__lte=stale_threshold)
                )
                .update(
                    dispatch_backend=AccountIntelligenceDispatchState.DispatchBackend.LOCAL_WORKER,
                    local_worker_locked_at=now,
                    local_worker_locked_by=(worker_id or "")[:64],
                    last_result="local_worker_claimed",
                    last_operational_issue="",
                )
            )
        if updated:
            state.refresh_from_db()
            claimed.append(state)
        if len(claimed) >= batch_size:
            break
    return claimed


def _mark_retryable_failure(state: AccountIntelligenceDispatchState, *, error_message: str) -> None:
    now = timezone.now()
    attempts = int(state.dispatch_attempt_count or 0)
    if attempts >= _max_stale_recoveries():
        state.pending_request = False
        state.last_result = "dead_letter"
        state.last_operational_issue = "dead_letter"
        state.next_attempt_at = None
    else:
        state.pending_request = True
        state.last_result = "worker_failed"
        state.last_operational_issue = "worker_failed"
        delay_seconds = min(1800, 2 ** min(max(1, attempts), 10))
        state.next_attempt_at = now + timezone.timedelta(seconds=delay_seconds)
    state.last_failed_at = now
    state.last_error_message = str(error_message or "")[:2000]
    state.local_worker_locked_at = None
    state.local_worker_locked_by = ""
    state.save()


def process_local_worker_requests(*, worker_id: str, limit: int | None = None) -> dict:
    claimed = claim_local_worker_requests(worker_id=worker_id, limit=limit)
    processed = 0
    failed = 0
    results: list[dict] = []
    for state in claimed:
        task_name = f"local-worker:{worker_id}"
        _update_dispatch_metrics(
            owner_id=state.owner_id,
            backend=AccountIntelligenceDispatchState.DispatchBackend.LOCAL_WORKER,
            result="local_worker_processing",
        )
        mark_account_intelligence_refresh_started(
            owner_id=state.owner_id,
            task_name=task_name,
            result="local_worker_started",
        )
        try:
            process_stub_account_intelligence_refresh(
                owner_id=state.owner_id,
                event={
                    "type": "accounts.intelligence.refresh.requested.v1",
                    "payload": {"owner_id": str(state.owner_id)},
                },
            )
            mark_account_intelligence_refresh_completed_for_task(
                owner_id=state.owner_id,
                task_name=task_name,
                result="local_worker_completed",
            )
            processed += 1
            results.append({"owner_id": str(state.owner_id), "result": "processed"})
        except Exception as exc:
            logger.exception(
                "[accounts.intelligence.worker] error processing owner_id=%s",
                state.owner_id,
            )
            with transaction.atomic():
                current = AccountIntelligenceDispatchState.objects.select_for_update().get(pk=state.pk)
                _mark_retryable_failure(current, error_message=f"local_worker_exception:{exc}")
            failed += 1
            results.append({"owner_id": str(state.owner_id), "result": "failed"})
    return {"claimed": len(claimed), "processed": processed, "failed": failed, "results": results}


def run_local_worker_cycle(*, worker_id: str, limit: int | None = None) -> dict:
    recovery = recover_stale_processing_intelligence_requests(limit=limit)
    if recovery["recovered"]:
        for state in AccountIntelligenceDispatchState.objects.filter(
            pending_request=True,
            last_result="processing_stale",
        )[: int(limit or _local_worker_batch_size())]:
            _mark_local_worker_pending(owner_id=state.owner_id)
    processing = process_local_worker_requests(worker_id=worker_id, limit=limit)
    summary = {"recover_stale_processing": recovery, "process": processing}
    logger.info("[accounts.intelligence.worker] cycle=%s", summary)
    return summary
