from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


OUTBOX_COMMANDS = {
    "accounts": "accounts_publish_outbox",
    "transactions": "transactions_publish_outbox",
    "alerts": "alerts_publish_outbox",
    "identity": "identity_publish_outbox",
    "payments": "payments_publish_outbox",
}


class Command(BaseCommand):
    help = "Wrapper unificado para publicar outbox por bounded context."

    def add_arguments(self, parser):
        parser.add_argument("context", help="Contexto canonico: accounts, transactions, alerts, identity o payments")
        parser.add_argument("--loop", action="store_true", help="Mantiene el publicador en polling continuo.")
        parser.add_argument("--sleep-seconds", type=int, default=5, help="Segundos entre ciclos.")
        parser.add_argument("--limit", type=int, default=200, help="Tamano maximo por ciclo.")
        parser.add_argument("--worker-id", default="", help="Identificador explicito del worker.")

    def handle(self, *args, **options):
        context = str(options.get("context") or "").strip()
        command_name = OUTBOX_COMMANDS.get(context)
        if not command_name:
            supported = ", ".join(sorted(OUTBOX_COMMANDS))
            raise CommandError(f"context no soportado: {context}. Soportados: {supported}")

        kwargs = {
            "loop": bool(options.get("loop")),
            "sleep_seconds": max(1, int(options.get("sleep_seconds") or 5)),
        }
        limit = max(1, int(options.get("limit") or 200))
        worker_id = str(options.get("worker_id") or "")

        if context == "accounts":
            kwargs.update(
                {
                    "batch_size": limit,
                    "worker_id": worker_id,
                }
            )
        else:
            kwargs.update(
                {
                    "limit": limit,
                    "worker_id": worker_id,
                }
            )

        call_command(command_name, **kwargs)
