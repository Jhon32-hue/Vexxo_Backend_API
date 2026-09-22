from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from notifications.deliveries.models import NotificationDelivery, NotificationStatus
from tasks.outbox_registry import OUTBOX_SPECS


class Command(BaseCommand):
    help = "Simula o aplica retencion sobre datos operativos no contables."

    def add_arguments(self, parser):
        parser.add_argument("--outbox-days", type=int, default=30)
        parser.add_argument("--read-notification-days", type=int, default=90)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        now = timezone.now()
        apply_changes = bool(options["apply"])
        result = {"outboxes": {}, "read_notifications": 0, "applied": apply_changes}

        with transaction.atomic():
            for name, spec in OUTBOX_SPECS.items():
                cutoff = now - timedelta(days=max(1, options["outbox_days"]))
                queryset = spec.model.objects.filter(published_at__lt=cutoff)
                count = queryset.count()
                result["outboxes"][name] = count
                if apply_changes:
                    queryset.delete()

            notification_cutoff = now - timedelta(days=max(1, options["read_notification_days"]))
            notifications = NotificationDelivery.objects.filter(
                status=NotificationStatus.READ,
                read_at__lt=notification_cutoff,
            )
            result["read_notifications"] = notifications.count()
            if apply_changes:
                notifications.delete()

            if not apply_changes:
                transaction.set_rollback(True)

        self.stdout.write(str(result))
