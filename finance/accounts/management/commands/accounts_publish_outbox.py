from __future__ import annotations

import socket
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from finance.accounts.models.outbox import DomainEventOutbox
from finance.accounts.services.event_service import publish_outbox_event


def _worker_id() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


class Command(BaseCommand):
    help = "Publica eventos pendientes del DomainEventOutbox (Patron Outbox)."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument(
            "--max-retries",
            type=int,
            default=max(1, int(getattr(settings, "ACCOUNTS_OUTBOX_MAX_RETRIES", 10))),
        )
        parser.add_argument("--lock-minutes", type=int, default=5)
        parser.add_argument(
            "--retry-cooldown-seconds",
            type=int,
            default=max(0, int(getattr(settings, "ACCOUNTS_OUTBOX_RETRY_BASE_SECONDS", 15))),
        )
        parser.add_argument("--event-type", type=str, default="")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--loop", action="store_true", help="Corre en loop hasta que no queden eventos.")
        parser.add_argument("--sleep-seconds", type=int, default=2, help="Sleep entre iteraciones en --loop.")

    def handle(self, *args, **opts):
        batch_size = opts["batch_size"]
        max_retries = max(1, int(opts["max_retries"]))
        lock_minutes = opts["lock_minutes"]
        retry_cooldown_seconds = max(0, int(opts["retry_cooldown_seconds"]))
        event_type_filter = (opts["event_type"] or "").strip()
        dry_run = bool(opts["dry_run"])
        loop = bool(opts["loop"])
        sleep_seconds = int(opts["sleep_seconds"])

        worker = _worker_id()
        self.stdout.write(self.style.SUCCESS(f"[outbox] worker={worker} dry_run={dry_run}"))

        published_total = 0
        failed_total = 0
        locked_total = 0
        scanned_total = 0
        dead_lettered_total = 0

        def _has_field(field_name: str) -> bool:
            return field_name in [x.name for x in DomainEventOutbox._meta.fields]

        def _dead_letter_exhausted(now):
            nonlocal dead_lettered_total
            exhausted = list(
                DomainEventOutbox.objects.select_for_update(skip_locked=True)
                .filter(
                    published_at__isnull=True,
                    status=DomainEventOutbox.Status.FAILED,
                    retry_count__gte=max_retries,
                    dead_lettered_at__isnull=True,
                )
                .order_by("occurred_at")[:batch_size]
            )
            for event in exhausted:
                event.last_publish_finished_at = event.last_publish_finished_at or now
                event.mark_dead_letter(
                    f"{event.last_error or 'retry_limit_reached'} | retries_exhausted={event.retry_count}",
                )
            dead_lettered_total += len(exhausted)

        def _run_once():
            nonlocal published_total, failed_total, locked_total, scanned_total, dead_lettered_total

            now = timezone.now()
            lock_expiry = now - timedelta(minutes=lock_minutes)
            retry_ready_at = now - timedelta(seconds=retry_cooldown_seconds)

            with transaction.atomic():
                _dead_letter_exhausted(now)

                qs = DomainEventOutbox.objects.select_for_update(skip_locked=True).filter(
                    published_at__isnull=True,
                    dead_lettered_at__isnull=True,
                )
                qs = qs.filter(
                    Q(status=DomainEventOutbox.Status.PENDING)
                    | (
                        Q(status=DomainEventOutbox.Status.FAILED)
                        & (
                            Q(next_attempt_at__isnull=False, next_attempt_at__lte=now)
                            | Q(next_attempt_at__isnull=True, last_publish_finished_at__isnull=True)
                            | Q(next_attempt_at__isnull=True, last_publish_finished_at__lte=retry_ready_at)
                        )
                    )
                )
                qs = qs.filter(retry_count__lt=max_retries)

                if event_type_filter:
                    qs = qs.filter(event_type=event_type_filter)

                has_lock_fields = _has_field("locked_at") and _has_field("locked_by")
                if has_lock_fields:
                    qs = qs.filter(Q(locked_at__isnull=True) | Q(locked_at__lt=lock_expiry))

                qs = qs.order_by("occurred_at")[:batch_size]
                events = list(qs)
                scanned_total += len(events)

                if not events:
                    return 0, 0, 0, 0

                if has_lock_fields:
                    ids = [e.pk for e in events]
                    DomainEventOutbox.objects.filter(pk__in=ids).update(
                        status=DomainEventOutbox.Status.PROCESSING,
                        locked_at=now,
                        locked_by=worker,
                    )
                    locked_total += len(ids)

            published = 0
            failed = 0
            dead_lettered = 0

            for ev in events:
                if dry_run:
                    self.stdout.write(
                        f"[dry-run] would publish id={ev.pk} type={ev.event_type} agg={ev.aggregate_type}:{ev.aggregate_id}"
                    )
                    published += 1
                    continue

                try:
                    publish_outbox_event(ev, publisher=worker)
                finally:
                    ev.refresh_from_db()
                    if _has_field("locked_at") and _has_field("locked_by"):
                        DomainEventOutbox.objects.filter(pk=ev.pk, locked_by=worker).update(
                            locked_at=None,
                            locked_by="",
                        )

                if ev.published_at:
                    published += 1
                elif ev.status == DomainEventOutbox.Status.DEAD_LETTER:
                    dead_lettered += 1
                else:
                    failed += 1

            published_total += published
            failed_total += failed
            dead_lettered_total += dead_lettered
            return len(events), published, failed, dead_lettered

        if loop:
            import time

            while True:
                count, pub, fail, dead = _run_once()
                self.stdout.write(f"[outbox] batch={count} published={pub} failed={fail} dead_lettered={dead}")
                if count == 0:
                    break
                time.sleep(sleep_seconds)
        else:
            count, pub, fail, dead = _run_once()
            self.stdout.write(f"[outbox] batch={count} published={pub} failed={fail} dead_lettered={dead}")

        self.stdout.write(
            self.style.SUCCESS(
                "[outbox] done "
                f"scanned={scanned_total} locked={locked_total} published={published_total} "
                f"failed={failed_total} dead_lettered={dead_lettered_total}"
            )
        )
