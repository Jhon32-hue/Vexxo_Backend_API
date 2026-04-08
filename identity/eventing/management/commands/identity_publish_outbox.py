from __future__ import annotations

from django.db import models
from django.core.management.base import BaseCommand
from django.utils import timezone

from identity.eventing.models import IdentityDomainEventOutbox
from identity.eventing.services import publish_identity_outbox_event


class Command(BaseCommand):
    help = "Publica eventos pendientes o fallidos del outbox de identity."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--worker-id", default="identity-publish-outbox")

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"] or 100))
        worker_id = str(options.get("worker_id") or "identity-publish-outbox")[:64]
        stale_threshold = timezone.now() - timezone.timedelta(minutes=15)
        qs = (
            IdentityDomainEventOutbox.objects.filter(
                published_at__isnull=True,
                status__in=[
                    IdentityDomainEventOutbox.Status.PENDING,
                    IdentityDomainEventOutbox.Status.FAILED,
                    IdentityDomainEventOutbox.Status.PROCESSING,
                ],
            )
            .exclude(status=IdentityDomainEventOutbox.Status.DEAD_LETTER)
            .filter(
                models.Q(next_attempt_at__isnull=True)
                | models.Q(next_attempt_at__lte=timezone.now())
                | models.Q(
                    status=IdentityDomainEventOutbox.Status.PROCESSING,
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
            publish_identity_outbox_event(event)
            event.refresh_from_db()
            if event.published_at:
                published += 1
            elif event.status in {IdentityDomainEventOutbox.Status.FAILED, IdentityDomainEventOutbox.Status.DEAD_LETTER}:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"identity outbox procesado: published={published} failed={failed} scanned={scanned}"
            )
        )
