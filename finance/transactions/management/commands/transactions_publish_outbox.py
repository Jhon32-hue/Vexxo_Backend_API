from __future__ import annotations

import socket

from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from finance.transactions.Models.outbox import TransactionDomainEventOutbox
from finance.transactions.event_service import publish_transaction_outbox_event


class Command(BaseCommand):
    help = "Publica eventos pendientes del outbox de transactions."

    def handle(self, *args, **options):
        worker_id = f"{socket.gethostname()}:{self.__class__.__name__}"
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
        ).order_by("occurred_at")[:200]
        processed = 0
        for event in qs:
            if not event.claim_for_processing(worker_id=worker_id):
                continue
            publish_transaction_outbox_event(event)
            processed += 1
        self.stdout.write(self.style.SUCCESS(f"transactions outbox processed={processed}"))
