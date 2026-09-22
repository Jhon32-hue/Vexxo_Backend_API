from __future__ import annotations

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from common.outbox_runtime import publish_pending_events
from tasks.outbox_registry import OUTBOX_SPECS


OUTBOX_COMMANDS = {
    name: spec.command_name for name, spec in OUTBOX_SPECS.items() if spec.command_name
}


class Command(BaseCommand):
    help = "Publica uno o varios outboxes desde el catalogo canonico de bounded contexts."

    def add_arguments(self, parser):
        parser.add_argument(
            "context",
            help="Contexto, lista separada por comas o all. Ej: debts,goals",
        )
        parser.add_argument("--loop", action="store_true", help="Mantiene polling continuo.")
        parser.add_argument("--sleep-seconds", type=int, default=5, help="Segundos entre ciclos.")
        parser.add_argument("--limit", type=int, default=200, help="Tamano maximo por contexto y ciclo.")
        parser.add_argument("--worker-id", default="", help="Identificador explicito del worker.")

    def _resolve_contexts(self, selector: str) -> list[str]:
        selector = str(selector or "").strip().lower()
        contexts = list(OUTBOX_SPECS) if selector == "all" else [item.strip() for item in selector.split(",")]
        unsupported = [item for item in contexts if item not in OUTBOX_SPECS]
        if unsupported:
            supported = ", ".join(sorted(OUTBOX_SPECS))
            raise CommandError(f"context no soportado: {', '.join(unsupported)}. Soportados: {supported}")
        return list(dict.fromkeys(contexts))

    def _run_context(self, *, context: str, limit: int, worker_id: str) -> None:
        spec = OUTBOX_SPECS[context]
        if spec.command_name:
            kwargs = {"worker_id": worker_id}
            kwargs["batch_size" if context == "accounts" else "limit"] = limit
            call_command(spec.command_name, **kwargs)
            return
        summary = publish_pending_events(
            model=spec.model,
            context=spec.context,
            limit=limit,
            worker_id=worker_id,
        )
        self.stdout.write(self.style.SUCCESS(f"{context} outbox cycle={summary}"))

    def handle(self, *args, **options):
        contexts = self._resolve_contexts(options.get("context"))
        loop = bool(options.get("loop"))
        sleep_seconds = max(1, int(options.get("sleep_seconds") or 5))
        limit = max(1, int(options.get("limit") or 200))
        worker_id = str(options.get("worker_id") or "")

        while True:
            for context in contexts:
                context_worker_id = worker_id or f"local-{context}"
                self._run_context(
                    context=context,
                    limit=limit,
                    worker_id=context_worker_id,
                )
            if not loop:
                break
            time.sleep(sleep_seconds)
