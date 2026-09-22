import json

from django.core.management.base import BaseCommand

from integrations.open_banking.provider_catalog import PROVIDERS


class Command(BaseCommand):
    help = "Muestra compuertas de credenciales y certificacion sin revelar secretos."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        rows = [
            {
                "provider": provider.code,
                "local_only": provider.local_only,
                "adapter_implemented": provider.implemented,
                "credentials_configured": provider.configured,
                "official_sandbox_certified": provider.certified,
                "available": provider.available,
            }
            for provider in PROVIDERS.values()
        ]
        local_ready = all(row["available"] for row in rows if row["local_only"])
        result = {"status": "ready" if local_ready else "blocked", "providers": rows}
        self.stdout.write(json.dumps(result, indent=2))
        if options["strict"] and not local_ready:
            raise SystemExit(1)
