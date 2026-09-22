import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.mobile.performance_fixtures import MOBILE_FIXTURE_SCALES, build_mobile_performance_fixture
from api.mobile.query_profiling import profile_mobile_endpoint


class Command(BaseCommand):
    help = "Compara consultas mobile con fixtures transaccionales de varios tamanos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--profiles",
            default="small,medium,large",
            help="Perfiles separados por coma: small,medium,large.",
        )
        parser.add_argument("--top", type=int, default=5)
        parser.add_argument(
            "--max-query-growth",
            type=int,
            default=0,
            help="Crecimiento maximo permitido entre el primer y ultimo perfil.",
        )
        parser.add_argument("--max-bootstrap-queries", type=int, default=100)
        parser.add_argument("--max-cached-bootstrap-queries", type=int, default=25)
        parser.add_argument("--max-sync-state-queries", type=int, default=25)

    def handle(self, *args, **options):
        profiles = [value.strip() for value in options["profiles"].split(",") if value.strip()]
        unknown = sorted(set(profiles) - set(MOBILE_FIXTURE_SCALES))
        if unknown:
            raise CommandError(f"Perfiles desconocidos: {', '.join(unknown)}")

        results = []
        for profile in profiles:
            with transaction.atomic():
                user, counts = build_mobile_performance_fixture(profile=profile)
                endpoints = {}
                bootstrap = profile_mobile_endpoint(
                    user=user,
                    endpoint="bootstrap",
                    top=options["top"],
                )
                versions = bootstrap.pop("section_versions")
                endpoints["bootstrap"] = bootstrap

                for report_name, endpoint, section_versions in (
                    ("bootstrap-cached", "bootstrap", versions),
                    ("sync-state", "sync-state", versions),
                ):
                    measurement = profile_mobile_endpoint(
                        user=user,
                        endpoint=endpoint,
                        top=options["top"],
                        section_versions=section_versions,
                    )
                    if measurement["status_code"] != 200:
                        raise CommandError(
                            f"{profile}/{report_name} devolvio HTTP {measurement['status_code']}."
                        )
                    measurement.pop("section_versions")
                    endpoints[report_name] = measurement
                results.append({"profile": profile, "fixture_counts": counts, "endpoints": endpoints})
                transaction.set_rollback(True)

        growth = {}
        if len(results) > 1:
            first = results[0]
            last = results[-1]
            for endpoint in ("bootstrap", "bootstrap-cached", "sync-state"):
                growth[endpoint] = {
                    "from": first["profile"],
                    "to": last["profile"],
                    "query_delta": (
                        last["endpoints"][endpoint]["query_count"]
                        - first["endpoints"][endpoint]["query_count"]
                    ),
                }

        self.stdout.write(json.dumps({"profiles": results, "growth": growth}, indent=2, sort_keys=True))
        regressions = [
            endpoint
            for endpoint, values in growth.items()
            if values["query_delta"] > options["max_query_growth"]
        ]
        if regressions:
            raise CommandError(
                "Crecimiento de consultas excedido en: " + ", ".join(sorted(regressions))
            )
        ceilings = {
            "bootstrap": options["max_bootstrap_queries"],
            "bootstrap-cached": options["max_cached_bootstrap_queries"],
            "sync-state": options["max_sync_state_queries"],
        }
        exceeded = [
            f"{result['profile']}/{endpoint}={result['endpoints'][endpoint]['query_count']}>{limit}"
            for result in results
            for endpoint, limit in ceilings.items()
            if result["endpoints"][endpoint]["query_count"] > limit
        ]
        if exceeded:
            raise CommandError("Presupuesto absoluto de consultas excedido: " + ", ".join(exceeded))
