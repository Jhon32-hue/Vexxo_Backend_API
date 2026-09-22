from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from common.db_locks import postgres_advisory_lock
from tasks.scheduled.models import ScheduledJobState
from tasks.scheduled.registry import SCHEDULED_JOBS, ScheduledJobSpec


logger = logging.getLogger(__name__)
SCHEDULER_LOCK_NAME = "vexxo.tasks.scheduled.run_due_jobs.v1"


def _is_due(state: ScheduledJobState, *, now, force: bool) -> bool:
    return force or state.next_run_at is None or state.next_run_at <= now


def _mark_started(state: ScheduledJobState, *, spec: ScheduledJobSpec, now) -> None:
    state.interval_seconds = spec.interval_seconds
    state.status = ScheduledJobState.Status.RUNNING
    state.run_count += 1
    state.last_started_at = now
    state.last_error = ""
    state.save(
        update_fields=[
            "interval_seconds",
            "status",
            "run_count",
            "last_started_at",
            "last_error",
            "updated_at",
        ]
    )


def _mark_succeeded(state: ScheduledJobState, *, spec: ScheduledJobSpec, result: dict) -> None:
    finished_at = timezone.now()
    state.status = ScheduledJobState.Status.SUCCEEDED
    state.consecutive_failures = 0
    state.last_finished_at = finished_at
    state.last_succeeded_at = finished_at
    state.next_run_at = finished_at + timedelta(seconds=spec.interval_seconds)
    state.last_result = result or {}
    state.last_error = ""
    state.save(
        update_fields=[
            "status",
            "consecutive_failures",
            "last_finished_at",
            "last_succeeded_at",
            "next_run_at",
            "last_result",
            "last_error",
            "updated_at",
        ]
    )


def _mark_failed(state: ScheduledJobState, *, spec: ScheduledJobSpec, exc: Exception) -> None:
    finished_at = timezone.now()
    state.status = ScheduledJobState.Status.FAILED
    state.failure_count += 1
    state.consecutive_failures += 1
    state.last_finished_at = finished_at
    state.next_run_at = finished_at + timedelta(seconds=spec.interval_seconds)
    state.last_result = {}
    state.last_error = str(exc)[:4000]
    state.save(
        update_fields=[
            "status",
            "failure_count",
            "consecutive_failures",
            "last_finished_at",
            "next_run_at",
            "last_result",
            "last_error",
            "updated_at",
        ]
    )


def run_scheduler_cycle(
    *,
    selector: str = "all",
    force: bool = False,
    job_specs: dict[str, ScheduledJobSpec] | None = None,
) -> dict:
    specs = job_specs or SCHEDULED_JOBS
    selected = specs if selector == "all" else {selector: specs[selector]}
    summary = {"lock_acquired": False, "executed": 0, "skipped": 0, "failed": 0, "jobs": {}}

    with postgres_advisory_lock(SCHEDULER_LOCK_NAME) as acquired:
        summary["lock_acquired"] = acquired
        if not acquired:
            return summary

        now = timezone.now()
        for name, spec in selected.items():
            state, _created = ScheduledJobState.objects.get_or_create(
                job_name=name,
                defaults={
                    "interval_seconds": spec.interval_seconds,
                    "next_run_at": now,
                },
            )
            if not _is_due(state, now=now, force=force):
                summary["skipped"] += 1
                summary["jobs"][name] = {"status": "not_due", "next_run_at": state.next_run_at}
                continue

            _mark_started(state, spec=spec, now=timezone.now())
            try:
                result = spec.runner() or {}
            except Exception as exc:  # A failed job must not stop the other jobs.
                logger.exception("Scheduled job failed: %s", name)
                _mark_failed(state, spec=spec, exc=exc)
                summary["failed"] += 1
                summary["jobs"][name] = {"status": "failed", "error": str(exc)[:4000]}
                continue

            _mark_succeeded(state, spec=spec, result=result)
            summary["executed"] += 1
            summary["jobs"][name] = {"status": "succeeded", "result": result}

    return summary
