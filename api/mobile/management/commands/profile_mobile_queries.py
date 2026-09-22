import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from api.mobile.query_profiling import profile_mobile_endpoint


class Command(BaseCommand):
    help = "Perfila consultas read-only de endpoints mobile para detectar N+1."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument(
            "--endpoint",
            choices=("bootstrap", "sync-state"),
            default="bootstrap",
        )
        parser.add_argument("--top", type=int, default=10)

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(email__iexact=options["email"])
        except user_model.DoesNotExist as exc:
            raise CommandError("No existe un usuario con ese email.") from exc

        payload = profile_mobile_endpoint(
            user=user,
            endpoint=options["endpoint"],
            top=options["top"],
        )
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        if payload["status_code"] != 200:
            raise CommandError(f"El endpoint devolvio HTTP {payload['status_code']}.")
