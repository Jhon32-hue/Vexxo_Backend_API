from __future__ import annotations

from django.core.management.base import BaseCommand

from identity.eventing.models import IdentityDomainEventOutbox
from identity.eventing.services import publish_identity_outbox_event


class Command(BaseCommand):
    help = "Publica eventos pendientes o fallidos del outbox de identity."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"] or 100))
        qs = (
            IdentityDomainEventOutbox.objects.filter(
                published_at__isnull=True,
                status__in=[
                    IdentityDomainEventOutbox.Status.PENDING,
                    IdentityDomainEventOutbox.Status.FAILED,
                ],
            )
            .order_by("occurred_at")[:limit]
        )

        published = 0
        failed = 0

        for event in qs:
            publish_identity_outbox_event(event)
            event.refresh_from_db()
            if event.published_at:
                published += 1
            elif event.status == IdentityDomainEventOutbox.Status.FAILED:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"identity outbox procesado: published={published} failed={failed} scanned={qs.count()}"
            )
        )
