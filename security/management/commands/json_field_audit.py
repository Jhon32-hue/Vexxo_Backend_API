import json

from django.core.management.base import BaseCommand

from security.json_field_audit import audit_json_fields


class Command(BaseCommand):
    help = "Audita JSONField y detecta candidatos externos sin la politica central; no modifica datos."

    def add_arguments(self, parser):
        parser.add_argument("--details", action="store_true")
        parser.add_argument("--scan-data", action="store_true")
        parser.add_argument("--limit-per-field", type=int, default=100)
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        result = audit_json_fields(
            scan_data=options["scan_data"],
            limit_per_field=max(1, options["limit_per_field"]),
        )
        if not options["details"]:
            result.pop("fields")
        self.stdout.write(json.dumps(result, indent=2))
        if options["strict"] and (
            result["unclassified_fields"] or result["policy_error_fields"] or result["invalid_rows"]
        ):
            raise SystemExit(1)
