from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from finance.debts.services import refresh_overdue_installments


class Command(BaseCommand):
    help = "Marca cuotas vencidas y recalcula el estado de sus deudas."

    def add_arguments(self, parser):
        parser.add_argument("--as-of", default="", help="Fecha de corte YYYY-MM-DD; por defecto hoy.")

    def handle(self, *args, **options):
        raw_as_of = str(options.get("as_of") or "").strip()
        as_of = parse_date(raw_as_of) if raw_as_of else None
        if raw_as_of and as_of is None:
            raise CommandError("--as-of debe usar formato YYYY-MM-DD.")
        updated = refresh_overdue_installments(as_of=as_of)
        self.stdout.write(self.style.SUCCESS(f"debt installments overdue updated={updated}"))
