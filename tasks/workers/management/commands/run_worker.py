from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


WORKER_COMMANDS = {
    "accounts.sync": "accounts_run_sync_worker",
    "accounts.intelligence": "accounts_run_intelligence_worker",
    "alerts.ai": "alerts_run_ai_worker",
    "transactions.voice": "transactions_run_inference_worker",
}


class Command(BaseCommand):
    help = "Wrapper unificado para workers locales durables por job_type."

    def add_arguments(self, parser):
        parser.add_argument("job_type", help="Job type canonico. Ej: accounts.sync, alerts.ai, transactions.voice")
        parser.add_argument("--loop", action="store_true", help="Mantiene el worker en polling continuo.")
        parser.add_argument("--sleep-seconds", type=int, default=5, help="Segundos entre ciclos.")
        parser.add_argument("--limit", type=int, default=25, help="Tamano maximo por ciclo.")
        parser.add_argument("--worker-id", default="", help="Identificador explicito del worker.")

    def handle(self, *args, **options):
        job_type = str(options.get("job_type") or "").strip()
        command_name = WORKER_COMMANDS.get(job_type)
        if not command_name:
            supported = ", ".join(sorted(WORKER_COMMANDS))
            raise CommandError(f"job_type no soportado: {job_type}. Soportados: {supported}")

        call_command(
            command_name,
            loop=bool(options.get("loop")),
            sleep_seconds=max(1, int(options.get("sleep_seconds") or 5)),
            limit=max(1, int(options.get("limit") or 25)),
            worker_id=str(options.get("worker_id") or ""),
        )

