from __future__ import annotations

from django.core.management.base import BaseCommand

from finance.transactions.transaction_inference_worker_service import (
    recover_stale_processing_inference_requests,
    redispatch_stale_queued_inference_requests,
)


class Command(BaseCommand):
    help = "Recupera solicitudes de inferencia de voz atascadas o sin despacho."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25, help="Tamano maximo por corrida.")

    def handle(self, *args, **options):
        limit = max(1, int(options.get("limit") or 25))
        queued = redispatch_stale_queued_inference_requests(
            source="transactions.inference.recover.command",
            limit=limit,
        )
        processing = recover_stale_processing_inference_requests(
            source="transactions.inference.recover.command",
            limit=limit,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"transactions inference recovery queued={queued} processing={processing}"
            )
        )
