from __future__ import annotations

import logging
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from finance.accounts.models import Account, SyncStatus
from finance.accounts.services.account_sync_service import (
    mark_account_sync_error,
    mark_account_sync_stale,
    schedule_account_sync,
)
from integrations_stub.banks.services import process_stub_account_sync
from integrations.open_banking.sync_service import process_open_banking_account_sync
from tasks.async_backends import AsyncExecutionMode, get_async_execution_fallback_mode, get_async_execution_mode

logger = logging.getLogger(__name__)


def accounts_sync_local_worker_enabled() -> bool:
    mode = get_async_execution_mode(
        "accounts.sync",
        cloud_tasks_enabled=False,
    )
    fallback_mode = get_async_execution_fallback_mode(
        "accounts.sync",
    )
    return mode == AsyncExecutionMode.LOCAL_WORKER or fallback_mode == AsyncExecutionMode.LOCAL_WORKER


def _local_worker_batch_size() -> int:
    return max(1, int(getattr(settings, "ACCOUNTS_SYNC_LOCAL_WORKER_BATCH_SIZE", 25) or 25))


def _dispatch_stale_after_seconds() -> int:
    return max(30, int(getattr(settings, "ACCOUNTS_SYNC_DISPATCH_STALE_AFTER_SECONDS", 120) or 120))


def _local_worker_stale_after_seconds() -> int:
    return max(30, int(getattr(settings, "ACCOUNTS_SYNC_LOCAL_WORKER_STALE_AFTER_SECONDS", 900) or 900))


def _processing_stale_after_seconds() -> int:
    return max(60, int(getattr(settings, "ACCOUNTS_SYNC_PROCESSING_STALE_AFTER_SECONDS", 900) or 900))


def _max_stale_recoveries() -> int:
    return max(1, int(getattr(settings, "ACCOUNTS_SYNC_MAX_STALE_RECOVERIES", 3) or 3))


def _runtime(account: Account) -> dict:
    return dict(getattr(account, "sync_runtime", None) or {})


def _save_runtime(account: Account, runtime: dict) -> None:
    account.sync_runtime = dict(runtime or {})
    account.save(update_fields=["sync_runtime", "updated_at"])


def _parse_runtime_dt(value):
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = timezone.datetime.fromisoformat(normalized)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, dt_timezone.utc)
        return parsed
    except Exception:
        return None


def _runtime_in_local_scope(runtime: dict) -> bool:
    backend = str((runtime or {}).get("dispatch_backend") or "")
    return backend in {"", "local_worker"}


def _update_runtime_dispatch(
    account: Account,
    *,
    backend: str = "",
    result: str = "",
    error: str = "",
    next_attempt_at=None,
    clear_lock: bool = False,
) -> dict:
    runtime = _runtime(account)
    runtime["dispatch_backend"] = (backend or runtime.get("dispatch_backend") or "")[:32]
    runtime["dispatch_attempt_count"] = int(runtime.get("dispatch_attempt_count") or 0) + 1
    runtime["last_dispatch_attempt_at"] = timezone.now().isoformat()
    runtime["last_dispatch_result"] = (result or "")[:64]
    runtime["last_dispatch_error"] = (error or "")[:2000]
    runtime["last_operational_issue"] = ""
    if next_attempt_at is None:
        runtime["next_attempt_at"] = None
    else:
        runtime["next_attempt_at"] = next_attempt_at.isoformat()
    if clear_lock:
        runtime["local_worker_locked_at"] = None
        runtime["local_worker_locked_by"] = ""
    return runtime


def note_sync_dispatch_attempt(*, account_id, backend: str = "", result: str = "", error: str = "") -> None:
    account = Account.objects.filter(pk=account_id).first()
    if account is None:
        return
    runtime = _update_runtime_dispatch(account, backend=backend, result=result, error=error)
    _save_runtime(account, runtime)


def mark_account_sync_local_worker_pending(*, account_id, result: str = "local_worker_pending") -> bool:
    account = Account.objects.filter(pk=account_id, external_id__gt="").first()
    if account is None:
        return False
    runtime = _update_runtime_dispatch(
        account,
        backend="local_worker",
        result=result,
        clear_lock=True,
    )
    runtime["last_operational_issue"] = ""
    _save_runtime(account, runtime)
    return True


def mark_account_sync_pipeline_unavailable(*, account_id, error: str = "pipeline_unavailable") -> bool:
    account = Account.objects.filter(pk=account_id).first()
    if account is None:
        return False
    runtime = _runtime(account)
    runtime["last_operational_issue"] = "pipeline_unavailable"
    runtime["last_dispatch_result"] = "pipeline_unavailable"
    runtime["last_dispatch_error"] = (error or "pipeline_unavailable")[:2000]
    runtime["last_dispatch_attempt_at"] = timezone.now().isoformat()
    _save_runtime(account, runtime)
    return True


def claim_local_worker_accounts(*, worker_id: str, limit: int | None = None) -> list[Account]:
    now = timezone.now()
    batch_size = int(limit or _local_worker_batch_size())
    lock_stale_threshold = now - timezone.timedelta(seconds=_local_worker_stale_after_seconds())
    due_accounts = list(
        Account.objects.filter(
            external_id__gt="",
            sync_runtime__current_phase="scheduled",
            next_sync_at__isnull=False,
            next_sync_at__lte=now,
        ).order_by("next_sync_at")[: batch_size * 3]
    )
    claimed: list[Account] = []
    for candidate in due_accounts:
        with transaction.atomic():
            account = Account.objects.select_for_update().filter(pk=candidate.pk).first()
            if account is None:
                continue
            runtime = _runtime(account)
            if str(runtime.get("current_phase") or "") != "scheduled":
                continue
            if not _runtime_in_local_scope(runtime):
                continue
            next_attempt_at = _parse_runtime_dt(runtime.get("next_attempt_at"))
            if next_attempt_at and next_attempt_at > now:
                continue
            locked_at = _parse_runtime_dt(runtime.get("local_worker_locked_at"))
            if locked_at and locked_at > lock_stale_threshold:
                continue
            runtime["dispatch_backend"] = "local_worker"
            runtime["local_worker_locked_at"] = now.isoformat()
            runtime["local_worker_locked_by"] = (worker_id or "")[:64]
            runtime["last_dispatch_result"] = "local_worker_claimed"
            runtime["last_operational_issue"] = ""
            _save_runtime(account, runtime)
            claimed.append(account)
        if len(claimed) >= batch_size:
            break
    return claimed


def recover_stale_processing_syncs(*, limit: int | None = None) -> dict:
    now = timezone.now()
    stale_threshold = now - timezone.timedelta(seconds=_processing_stale_after_seconds())
    batch_size = int(limit or _local_worker_batch_size())
    candidates = list(
        Account.objects.filter(
            external_id__gt="",
            sync_status=SyncStatus.RUNNING,
            sync_runtime__current_phase="running",
        ).order_by("last_sync_status_at")[:batch_size]
    )
    scanned = 0
    recovered = 0
    dead_lettered = 0
    rescheduled = 0
    for candidate in candidates:
        with transaction.atomic():
            account = Account.objects.select_for_update().filter(pk=candidate.pk).first()
            if account is None:
                continue
            runtime = _runtime(account)
            if str(runtime.get("current_phase") or "") != "running":
                continue
            if not _runtime_in_local_scope(runtime):
                continue
            started_at = _parse_runtime_dt(runtime.get("started_at")) or account.last_sync_status_at
            if started_at is None or started_at > stale_threshold:
                continue
            scanned += 1
            stale_recovery_count = int(runtime.get("stale_recovery_count") or 0) + 1
            runtime["stale_recovery_count"] = stale_recovery_count
            runtime["last_recovered_at"] = now.isoformat()
            runtime["last_operational_issue"] = "processing_stale"
            runtime["local_worker_locked_at"] = None
            runtime["local_worker_locked_by"] = ""
            account.sync_runtime = runtime
            mark_account_sync_stale(
                account,
                metadata={"source": "accounts.sync_worker.recover_stale_processing"},
            )
            if stale_recovery_count >= _max_stale_recoveries():
                runtime = _runtime(account)
                runtime["last_operational_issue"] = "dead_letter"
                runtime["next_attempt_at"] = None
                _save_runtime(account, runtime)
                dead_lettered += 1
                continue
            next_run_at = now + timedelta(seconds=_dispatch_stale_after_seconds())
            schedule_account_sync(
                account=account,
                data={"run_at": next_run_at, "delay_minutes": 1},
            )
            runtime = _runtime(account)
            runtime["stale_recovery_count"] = stale_recovery_count
            runtime["last_recovered_at"] = now.isoformat()
            account.sync_runtime = runtime
            account.save(update_fields=["sync_runtime", "updated_at"])
            recovered += 1
        if accounts_sync_local_worker_enabled() and mark_account_sync_local_worker_pending(account_id=candidate.pk):
            rescheduled += 1
    return {
        "scanned": scanned,
        "recovered": recovered,
        "dead_lettered": dead_lettered,
        "rescheduled": rescheduled,
    }


def process_local_worker_accounts(*, worker_id: str, limit: int | None = None) -> dict:
    claimed = claim_local_worker_accounts(worker_id=worker_id, limit=limit)
    processed = 0
    failed = 0
    results: list[dict] = []
    for account in claimed:
        runtime = _runtime(account)
        sync_run_id = str(runtime.get("current_run_id") or "")[:64]
        try:
            processor = process_stub_account_sync if account.provider == "local_mock" else process_open_banking_account_sync
            processor(
                account=account,
                event={
                    "type": "accounts.sync.scheduled.v1",
                    "payload": {
                        "account_id": str(account.pk),
                        "provider": account.provider,
                        "sync_run_id": sync_run_id,
                    },
                },
                **({"mode": "success", "next_sync_at": timezone.now() + timedelta(minutes=30), "duration_ms": 50} if account.provider == "local_mock" else {}),
            )
            refreshed = Account.objects.get(pk=account.pk)
            updated_runtime = _runtime(refreshed)
            updated_runtime["local_worker_locked_at"] = None
            updated_runtime["local_worker_locked_by"] = ""
            updated_runtime["last_operational_issue"] = ""
            refreshed.sync_runtime = updated_runtime
            refreshed.save(update_fields=["sync_runtime", "updated_at"])
            processed += 1
            results.append({"account_id": str(account.pk), "result": "processed"})
        except Exception as exc:
            logger.exception("[accounts.sync.worker] error account_id=%s", account.pk)
            failed += 1
            with transaction.atomic():
                current = Account.objects.select_for_update().filter(pk=account.pk).first()
                if current is None:
                    continue
                current_runtime = _runtime(current)
                sync_run_id = str(current_runtime.get("current_run_id") or sync_run_id)[:64]
                retry_minutes = min(30, max(1, 2 ** min(int(current.sync_attempts or 0) + 1, 5)))
                mark_account_sync_error(
                    account=current,
                    data={
                        "message": f"local_worker_exception:{exc}",
                        "retry_in_minutes": retry_minutes,
                        "sync_run_id": sync_run_id,
                    },
                    metadata={"source": "accounts.sync_worker.process"},
                )
                if int(current.sync_attempts or 0) < _max_stale_recoveries():
                    next_run_at = timezone.now() + timedelta(minutes=retry_minutes)
                    schedule_account_sync(
                        account=current,
                        data={"run_at": next_run_at, "delay_minutes": retry_minutes},
                    )
                    if accounts_sync_local_worker_enabled():
                        mark_account_sync_local_worker_pending(account_id=current.pk, result="local_worker_retry_pending")
                else:
                    failed_runtime = _runtime(current)
                    failed_runtime["last_operational_issue"] = "dead_letter"
                    failed_runtime["local_worker_locked_at"] = None
                    failed_runtime["local_worker_locked_by"] = ""
                    current.sync_runtime = failed_runtime
                    current.save(update_fields=["sync_runtime", "updated_at"])
            results.append({"account_id": str(account.pk), "result": "failed"})
    return {"claimed": len(claimed), "processed": processed, "failed": failed, "results": results}


def run_local_worker_cycle(*, worker_id: str, limit: int | None = None) -> dict:
    stale_processing = recover_stale_processing_syncs(limit=limit)
    processing = process_local_worker_accounts(worker_id=worker_id, limit=limit)
    summary = {
        "recover_stale_processing": stale_processing,
        "process": processing,
    }
    logger.info("[accounts.sync.worker] cycle=%s", summary)
    return summary
