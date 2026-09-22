import json

from django.core.management.base import BaseCommand, CommandError

from security.api_surface_audit import audit_api_surfaces


class Command(BaseCommand):
    help = "Inventaria filtros, busqueda y ordering declarados por las APIs DRF."

    def add_arguments(self, parser):
        parser.add_argument("--details", action="store_true")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        result = audit_api_surfaces()
        if not options["details"]:
            result.pop("views")
        self.stdout.write(json.dumps(result, indent=2))
        if options["strict"] and (result["unsafe_view_count"] or result["unsafe_code_count"]):
            raise CommandError("Se detectaron APIs con filtros no allowlisted.")
