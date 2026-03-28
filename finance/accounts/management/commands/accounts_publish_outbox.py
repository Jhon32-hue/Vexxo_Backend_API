from __future__ import annotations

import socket
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from finance.accounts.models.outbox import DomainEventOutbox
from finance.accounts.services.event_service import publish_outbox_event


def _worker_id() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


class Command(BaseCommand):
    help = "Publica eventos pendientes del DomainEventOutbox (Patrón Outbox)."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--max-retries", type=int, default=10)
        parser.add_argument("--lock-minutes", type=int, default=5)
        parser.add_argument("--event-type", type=str, default="")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--loop", action="store_true", help="Corre en loop hasta que no queden eventos.")
        parser.add_argument("--sleep-seconds", type=int, default=2, help="Sleep entre iteraciones en --loop.")

    def handle(self, *args, **opts):
        batch_size = opts["batch_size"]
        max_retries = opts["max_retries"]
        lock_minutes = opts["lock_minutes"]
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

        def _run_once():
            nonlocal published_total, failed_total, locked_total, scanned_total

            now = timezone.now()
            lock_expiry = now - timedelta(minutes=lock_minutes)

            # 1) Selección y lock de eventos (en transacción)
            with transaction.atomic():
                qs = DomainEventOutbox.objects.select_for_update(skip_locked=True).filter(
                    published_at__isnull=True,
                )

                # Si tu modelo tiene status, úsalo; si no, ignoramos
                if hasattr(DomainEventOutbox, "Status") and "status" in [f.name for f in DomainEventOutbox._meta.fields]:
                    qs = qs.filter(status=getattr(DomainEventOutbox.Status, "PENDING", "pending"))

                qs = qs.filter(retry_count__lt=max_retries)

                if event_type_filter:
                    qs = qs.filter(event_type=event_type_filter)

                # Locking opcional (si existen locked_at/locked_by)
                has_lock_fields = all(
                    f in [x.name for x in DomainEventOutbox._meta.fields]
                    for f in ("locked_at", "locked_by")
                )

                if has_lock_fields:
                    qs = qs.filter(Q(locked_at__isnull=True) | Q(locked_at__lt=lock_expiry))

                # Orden estable (FIFO)
                qs = qs.order_by("occurred_at")[:batch_size]

                events = list(qs)
                scanned_total += len(events)

                if not events:
                    return 0, 0, 0

                if has_lock_fields:
                    ids = [e.pk for e in events]
                    DomainEventOutbox.objects.filter(pk__in=ids).update(locked_at=now, locked_by=worker)
                    locked_total += len(ids)

            # 2) Publicación fuera del lock de selección
            published = 0
            failed = 0

            for ev in events:
                if dry_run:
                    self.stdout.write(f"[dry-run] would publish id={ev.pk} type={ev.event_type} agg={ev.aggregate_type}:{ev.aggregate_id}")
                    published += 1
                    continue

                try:
                    publish_outbox_event(ev)
                    # publish_outbox_event ya marca published_at o incrementa retry_count+last_error.
                    # Actualizamos status si existe.
                    if hasattr(DomainEventOutbox, "Status") and "status" in [f.name for f in DomainEventOutbox._meta.fields]:
                        DomainEventOutbox.objects.filter(pk=ev.pk, published_at__isnull=False).update(
                            status=getattr(DomainEventOutbox.Status, "PUBLISHED", "published"),
                            locked_at=None if _has_field("locked_at") else None,
                            locked_by="" if _has_field("locked_by") else "",
                        )
                    published += 1
                except Exception:
                    failed += 1
                    # Si status existe, marcar FAILED cuando supera retries
                    if hasattr(DomainEventOutbox, "Status") and "status" in [f.name for f in DomainEventOutbox._meta.fields]:
                        # Si ya llegó al límite de retries, marca failed
                        DomainEventOutbox.objects.filter(pk=ev.pk, retry_count__gte=max_retries).update(
                            status=getattr(DomainEventOutbox.Status, "FAILED", "failed")
                        )
                finally:
                    # liberar lock si existe
                    if _has_field("locked_at") and _has_field("locked_by"):
                        DomainEventOutbox.objects.filter(pk=ev.pk, locked_by=worker).update(
                            locked_at=None,
                            locked_by="",
                        )

            published_total += published
            failed_total += failed
            return len(events), published, failed

        def _has_field(field_name: str) -> bool:
            return field_name in [x.name for x in DomainEventOutbox._meta.fields]

        # loop mode
        if loop:
            import time
            while True:
                count, pub, fail = _run_once()
                self.stdout.write(f"[outbox] batch={count} published={pub} failed={fail}")
                if count == 0:
                    break
                time.sleep(sleep_seconds)
        else:
            count, pub, fail = _run_once()
            self.stdout.write(f"[outbox] batch={count} published={pub} failed={fail}")

        self.stdout.write(
            self.style.SUCCESS(
                f"[outbox] done scanned={scanned_total} locked={locked_total} published={published_total} failed={failed_total}"
            )
        )
