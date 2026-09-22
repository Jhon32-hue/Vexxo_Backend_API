from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone

from alerts.alerts.models.ai_dispatch import AlertAiDispatchState
from finance.accounts.models import Account, AccountIntelligenceDispatchState
from finance.transactions.Models.inference import TransactionInferenceRequest
from tasks.scheduled.models import ScheduledJobState
from documents.ocr_requests.models import OcrRequest


def _status_counts(model) -> str:
    rows = model.objects.values("status").annotate(total=Count("pk")).order_by("status")
    return ",".join(f"{row['status']}={row['total']}" for row in rows) or "empty"


class Command(BaseCommand):
    help = "Resume las colas durables de workers locales."

    def add_arguments(self, parser):
        parser.add_argument("job_type", nargs="?", default="all")

    def handle(self, *args, **options):
        requested = str(options["job_type"] or "all").lower()
        supported = {
            "accounts.sync",
            "accounts.intelligence",
            "alerts.ai",
            "transactions.voice",
            "scheduler",
            "documents.ocr",
        }
        if requested != "all" and requested not in supported:
            raise CommandError(f"Worker no soportado: {requested}")

        selected = supported if requested == "all" else {requested}
        now = timezone.now()
        if "accounts.sync" in selected:
            counts = Account.objects.values("sync_status").annotate(total=Count("pk")).order_by("sync_status")
            summary = ",".join(f"{row['sync_status']}={row['total']}" for row in counts) or "empty"
            self.stdout.write(
                f"accounts.sync: backend={settings.ASYNC_EXECUTION_MODE_ACCOUNTS_SYNC} states={summary}"
            )
        if "accounts.intelligence" in selected:
            queryset = AccountIntelligenceDispatchState.objects.all()
            stale_before = now - timedelta(
                seconds=int(getattr(settings, "ACCOUNTS_INTELLIGENCE_LOCAL_WORKER_STALE_AFTER_SECONDS", 900))
            )
            self.stdout.write(
                "accounts.intelligence: "
                f"backend={settings.ASYNC_EXECUTION_MODE_ACCOUNTS_INTELLIGENCE} "
                f"pending={queryset.filter(pending_request=True).count()} "
                f"stale_locks={queryset.filter(local_worker_locked_at__lt=stale_before).count()}"
            )
        if "alerts.ai" in selected:
            self.stdout.write(
                f"alerts.ai: backend={settings.ASYNC_EXECUTION_MODE_ALERTS_AI} states={_status_counts(AlertAiDispatchState)}"
            )
        if "transactions.voice" in selected:
            self.stdout.write(
                "transactions.voice: "
                f"backend={settings.ASYNC_EXECUTION_MODE_TRANSACTIONS_VOICE} "
                f"states={_status_counts(TransactionInferenceRequest)}"
            )
        if "documents.ocr" in selected:
            self.stdout.write(
                f"documents.ocr: backend=local_worker states={_status_counts(OcrRequest)}"
            )
        if "scheduler" in selected:
            states = ScheduledJobState.objects.order_by("job_name")
            if not states.exists():
                self.stdout.write("scheduler: states=empty")
            for state in states:
                self.stdout.write(
                    "scheduler: "
                    f"job={state.job_name} status={state.status} runs={state.run_count} "
                    f"failures={state.failure_count} next_run_at={state.next_run_at or '-'} "
                    f"last_error={state.last_error or '-'}"
                )
