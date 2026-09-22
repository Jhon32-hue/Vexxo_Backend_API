from contextlib import nullcontext
from unittest.mock import patch

from django.test import TestCase

from tasks.scheduled.models import ScheduledJobState
from tasks.scheduled.registry import ScheduledJobSpec
from tasks.scheduled.scheduler import run_scheduler_cycle


class SchedulerTests(TestCase):
    def test_cycle_persists_success_and_skips_job_until_next_run(self):
        calls = []
        spec = ScheduledJobSpec(
            name="test.success",
            interval_seconds=60,
            runner=lambda: calls.append("ran") or {"processed": 3},
        )

        first = run_scheduler_cycle(force=True, job_specs={spec.name: spec})
        second = run_scheduler_cycle(job_specs={spec.name: spec})

        state = ScheduledJobState.objects.get(job_name=spec.name)
        self.assertTrue(first["lock_acquired"])
        self.assertEqual(first["executed"], 1)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(calls, ["ran"])
        self.assertEqual(state.status, ScheduledJobState.Status.SUCCEEDED)
        self.assertEqual(state.last_result, {"processed": 3})
        self.assertEqual(state.run_count, 1)

    def test_failed_job_is_recorded_without_losing_scheduler_state(self):
        def fail():
            raise RuntimeError("test scheduler failure")

        spec = ScheduledJobSpec(name="test.failure", interval_seconds=60, runner=fail)

        summary = run_scheduler_cycle(force=True, job_specs={spec.name: spec})

        state = ScheduledJobState.objects.get(job_name=spec.name)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(state.status, ScheduledJobState.Status.FAILED)
        self.assertEqual(state.failure_count, 1)
        self.assertIn("test scheduler failure", state.last_error)

    @patch(
        "tasks.scheduled.scheduler.postgres_advisory_lock",
        return_value=nullcontext(False),
    )
    def test_cycle_exits_without_work_when_another_scheduler_holds_lock(self, _lock):
        spec = ScheduledJobSpec(
            name="test.locked",
            interval_seconds=60,
            runner=lambda: {"unexpected": True},
        )

        summary = run_scheduler_cycle(force=True, job_specs={spec.name: spec})

        self.assertFalse(summary["lock_acquired"])
        self.assertFalse(ScheduledJobState.objects.exists())
