import json

from django.core.management.base import BaseCommand

from documents.files.migration_service import migrate_historical_documents


class Command(BaseCommand):
    help = "Cifra progresivamente documentos historicos no cifrados en lotes acotados."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(migrate_historical_documents(limit=options["limit"]), default=str))
