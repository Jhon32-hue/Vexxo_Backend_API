from __future__ import annotations

import time

from django.db import models
from django.core.management.base import BaseCommand
from django.utils import timezone

from alerts.alerts.event_service import publish_alert_outbox_event
from alerts.alerts.models import AlertDomainEventOutbox


class Command(BaseCommand):
    help = "Publica eventos pendientes o fallidos del outbox de alerts."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--worker-id", default="alerts-publish-outbox")
        parser.add_argument("--loop", action="store_true", help="Mantiene el worker en polling continuo.")
        parser.add_argument("--sleep-seconds", type=int, default=5, help="Segundos de espera entre ciclos en modo loop.")

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"] or 100))
        worker_id = str(options.get("worker_id") or "alerts-publish-outbox")[:64]
        loop = bool(options.get("loop"))
        sleep_seconds = max(1, int(options.get("sleep_seconds") or 5))

        def _run_once() -> dict:
            stale_threshold = timezone.now() - timezone.timedelta(minutes=15)
            qs = (
                AlertDomainEventOutbox.objects.filter(
                    published_at__isnull=True,
                    status__in=[
                        AlertDomainEventOutbox.Status.PENDING,
                        AlertDomainEventOutbox.Status.FAILED,
                        AlertDomainEventOutbox.Status.PROCESSING,
                    ],
                )
                .exclude(status=AlertDomainEventOutbox.Status.DEAD_LETTER)
                .filter(
                    models.Q(next_attempt_at__isnull=True)
                    | models.Q(next_attempt_at__lte=timezone.now())
                    | models.Q(
                        status=AlertDomainEventOutbox.Status.PROCESSING,
                        locked_at__lte=stale_threshold,
                    )
                )
                .order_by("occurred_at")[:limit]
            )

            published = 0
            failed = 0
            scanned = 0

            for event in qs:
                scanned += 1
                if not event.claim_for_processing(worker_id=worker_id):
                    continue
                publish_alert_outbox_event(event)
                event.refresh_from_db()
                if event.published_at:
                    published += 1
                elif event.status in {AlertDomainEventOutbox.Status.FAILED, AlertDomainEventOutbox.Status.DEAD_LETTER}:
                    failed += 1
            return {"published": published, "failed": failed, "scanned": scanned}

        while True:
            summary = _run_once()
            self.stdout.write(self.style.SUCCESS(f"alerts outbox cycle={summary}"))
            if not loop:
                break
            time.sleep(sleep_seconds)
