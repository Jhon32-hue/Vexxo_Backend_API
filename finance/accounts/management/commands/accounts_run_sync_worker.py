from __future__ import annotations

import socket
import time

from django.core.management.base import BaseCommand

from finance.accounts.services.sync_worker_service import run_local_worker_cycle


class Command(BaseCommand):
    help = "Ejecuta el worker local durable de sync externo de cuentas."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Mantiene el worker en polling continuo.")
        parser.add_argument("--sleep-seconds", type=int, default=5, help="Segundos de espera entre ciclos en modo loop.")
        parser.add_argument("--limit", type=int, default=25, help="Tamano maximo por ciclo.")
        parser.add_argument("--worker-id", default="", help="Identificador explicito del worker.")

    def handle(self, *args, **options):
        worker_id = str(options.get("worker_id") or f"{socket.gethostname()}:{self.__class__.__name__}")[:64]
        loop = bool(options.get("loop"))
        sleep_seconds = max(1, int(options.get("sleep_seconds") or 5))
        limit = max(1, int(options.get("limit") or 25))
        while True:
            summary = run_local_worker_cycle(worker_id=worker_id, limit=limit)
            self.stdout.write(self.style.SUCCESS(f"accounts sync worker cycle={summary}"))
            if not loop:
                break
            time.sleep(sleep_seconds)
