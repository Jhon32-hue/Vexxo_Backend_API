from __future__ import annotations

import socket
import time

from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from finance.transactions.Models.outbox import TransactionDomainEventOutbox
from finance.transactions.event_service import publish_transaction_outbox_event


class Command(BaseCommand):
    help = "Publica eventos pendientes del outbox de transactions."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--worker-id", default="")
        parser.add_argument("--loop", action="store_true", help="Mantiene el worker en polling continuo.")
        parser.add_argument("--sleep-seconds", type=int, default=5, help="Segundos de espera entre ciclos en modo loop.")

    def handle(self, *args, **options):
        worker_id = str(options.get("worker_id") or f"{socket.gethostname()}:{self.__class__.__name__}")[:64]
        limit = max(1, int(options.get("limit") or 200))
        loop = bool(options.get("loop"))
        sleep_seconds = max(1, int(options.get("sleep_seconds") or 5))

        def _run_once() -> dict:
            stale_threshold = timezone.now() - timezone.timedelta(minutes=15)
            qs = TransactionDomainEventOutbox.objects.filter(
                models.Q(
                    status__in=[
                        TransactionDomainEventOutbox.Status.PENDING,
                        TransactionDomainEventOutbox.Status.FAILED,
                    ]
                )
                | models.Q(
                    status=TransactionDomainEventOutbox.Status.PROCESSING,
                    locked_at__lte=stale_threshold,
                )
            ).filter(
                models.Q(next_attempt_at__isnull=True)
                | models.Q(next_attempt_at__lte=timezone.now())
                | models.Q(status=TransactionDomainEventOutbox.Status.PROCESSING)
            ).order_by("occurred_at")[:limit]
            processed = 0
            failed = 0
            scanned = 0
            for event in qs:
                scanned += 1
                if not event.claim_for_processing(worker_id=worker_id):
                    continue
                publish_transaction_outbox_event(event)
                event.refresh_from_db()
                if event.published_at:
                    processed += 1
                else:
                    failed += 1
            return {"processed": processed, "failed": failed, "scanned": scanned}

        while True:
            summary = _run_once()
            self.stdout.write(self.style.SUCCESS(f"transactions outbox cycle={summary}"))
            if not loop:
                break
            time.sleep(sleep_seconds)
