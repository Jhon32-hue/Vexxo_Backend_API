from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from security.query_safety import safe_order_by

from tasks.outbox_registry import OUTBOX_SPECS


class Command(BaseCommand):
    help = "Resume pendientes, fallos y dead letters de los outboxes locales."

    def add_arguments(self, parser):
        parser.add_argument("context", nargs="?", default="all")

    def handle(self, *args, **options):
        requested = str(options["context"] or "all").lower()
        if requested != "all" and requested not in OUTBOX_SPECS:
            raise CommandError(f"Contexto no soportado: {requested}")
        specs = OUTBOX_SPECS if requested == "all" else {requested: OUTBOX_SPECS[requested]}
        for name, spec in specs.items():
            model = spec.model
            fields = {field.name for field in model._meta.get_fields()}
            queryset = model.objects.all()
            pending = queryset.filter(published_at__isnull=True)
            if "dead_lettered_at" in fields:
                pending = pending.filter(dead_lettered_at__isnull=True)
            elif "dead_letter_at" in fields:
                pending = pending.filter(dead_letter_at__isnull=True)
            failed = queryset.filter(~Q(last_error="")).count() if "last_error" in fields else 0
            dead = 0
            if "dead_lettered_at" in fields:
                dead = queryset.filter(dead_lettered_at__isnull=False).count()
            elif "dead_letter_at" in fields:
                dead = queryset.filter(dead_letter_at__isnull=False).count()
            timestamp_field = "created_at" if "created_at" in fields else "occurred_at"
            oldest = safe_order_by(pending, timestamp_field, allowed_fields={timestamp_field}).values_list(timestamp_field, flat=True).first()
            self.stdout.write(
                f"{name}: pending={pending.count()} failed={failed} "
                f"dead_letter={dead} oldest_pending={oldest or '-'}"
            )
