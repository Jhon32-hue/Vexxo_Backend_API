from django.core.management.base import BaseCommand

from api.mobile.market_data import build_mobile_market_snapshot


class Command(BaseCommand):
    help = "Refresca el cache BFF de mercados mobile para las monedas base principales."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bases",
            nargs="+",
            default=["COP", "USD", "EUR"],
            help="Monedas base a precalentar en cache.",
        )

    def handle(self, *args, **options):
        bases = [str(item).upper() for item in options["bases"]]
        for base in bases:
            snapshot = build_mobile_market_snapshot(base_currency=base)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{base}: {snapshot['provider_status']} provider={snapshot['provider']} "
                    f"pairs={len(snapshot['fx_pairs'])} series={len(snapshot.get('series', []))}"
                )
            )
