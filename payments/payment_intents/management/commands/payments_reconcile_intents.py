from __future__ import annotations

from django.core.management.base import BaseCommand

from payments.payment_intents.models import PaymentIntent


class Command(BaseCommand):
    help = "Revisa intents de pago para detectar faltantes de settlement o casos operativos abiertos."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"] or 100))
        qs = PaymentIntent.objects.order_by("-created_at")[:limit]

        missing_settlement = 0
        operational_cases = 0

        for intent in qs:
            if intent.status in {PaymentIntent.Status.SUCCEEDED, PaymentIntent.Status.SETTLED} and not intent.settlement_records.exists():
                missing_settlement += 1
            if intent.operational_cases.filter(status__in=["open", "investigating"]).exists():
                operational_cases += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"payments reconcile: scanned={qs.count()} missing_settlement={missing_settlement} open_operational_cases={operational_cases}"
            )
        )
