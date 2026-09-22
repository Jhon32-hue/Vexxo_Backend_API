from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from tasks.scheduled.registry import SCHEDULED_JOBS
from tasks.scheduled.scheduler import run_scheduler_cycle


class Command(BaseCommand):
    help = "Ejecuta el catalogo central de jobs periodicos con lock singleton en PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("job", nargs="?", default="all")
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--sleep-seconds", type=int, default=15)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        selector = str(options.get("job") or "all").strip().lower()
        if selector != "all" and selector not in SCHEDULED_JOBS:
            raise CommandError(
                f"Job no soportado: {selector}. Soportados: {', '.join(sorted(SCHEDULED_JOBS))}"
            )
        loop = bool(options.get("loop"))
        sleep_seconds = max(1, int(options.get("sleep_seconds") or 15))
        force = bool(options.get("force"))

        while True:
            summary = run_scheduler_cycle(selector=selector, force=force)
            self.stdout.write(f"scheduler cycle={summary}")
            if not loop:
                if summary["failed"]:
                    raise CommandError("Uno o mas jobs periodicos fallaron.")
                break
            time.sleep(sleep_seconds)
