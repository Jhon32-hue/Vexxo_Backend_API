from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from observability.healthchecks import runtime_health


class Command(BaseCommand):
    help = "Muestra el perfil local efectivo y la salud de sus dependencias."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        health = runtime_health()
        self.stdout.write(f"environment={getattr(settings, 'ENV', 'local')}")
        self.stdout.write(f"debug={bool(settings.DEBUG)}")
        self.stdout.write(f"database={settings.DATABASES['default']['ENGINE']}")
        self.stdout.write(f"database_ok={health['checks']['database']['ok']}")
        for name in (
            "ACCOUNTS_SYNC",
            "ACCOUNTS_INTELLIGENCE",
            "ALERTS_AI",
            "IDENTITY_CONSENTS",
            "TRANSACTIONS_VOICE",
        ):
            value = getattr(settings, f"ASYNC_EXECUTION_MODE_{name}", "")
            self.stdout.write(f"async.{name.lower()}={value}")
        if options["strict"] and not health["ok"]:
            raise CommandError("El runtime local no esta listo.")
