from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from payments.scheduled_payments.services import process_due_schedule_runs


class Command(BaseCommand):
    help = "Procesa ocurrencias de pagos programados, actualiza due/overdue y emite recordatorios correlacionados."

    def add_arguments(self, parser):
        parser.add_argument("--as-of", dest="as_of", help="Fecha YYYY-MM-DD para evaluar vencimiento.")
        parser.add_argument("--limit", dest="limit", type=int, default=200)

    def handle(self, *args, **options):
        as_of_value = options.get("as_of")
        try:
            as_of_date = date.fromisoformat(as_of_value) if as_of_value else None
        except ValueError as exc:
            raise CommandError("Debes usar --as-of con formato YYYY-MM-DD.") from exc

        result = process_due_schedule_runs(as_of_date=as_of_date, limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(
                "processed={processed} reminders_sent={reminders_sent} due_marked={due_marked} "
                "overdue_marked={overdue_marked} as_of={as_of_date}".format(**result)
            )
        )
