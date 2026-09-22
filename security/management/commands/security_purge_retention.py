import json

from django.core.management.base import BaseCommand

from security.retention import purge_security_retention


class Command(BaseCommand):
    help = "Purga por lotes auditoria, throttles, challenges y grants vencidos segun politica."

    def add_arguments(self, parser):
        parser.add_argument("--limit-per-model", type=int, default=500)

    def handle(self, *args, **options):
        result = purge_security_retention(limit_per_model=options["limit_per_model"])
        self.stdout.write(json.dumps(result, indent=2))
