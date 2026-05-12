import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from payments.scheduled_payments.services import get_schedule_run_operational_metrics


class Command(BaseCommand):
    help = "Entrega metricas operativas del modulo de pagos programados."

    def add_arguments(self, parser):
        parser.add_argument("--owner-id", type=int, help="Filtra metricas para un owner especifico.")
        parser.add_argument(
            "--fail-on-anomalies",
            action="store_true",
            help="Termina con error si detecta conflictos o multiples runs abiertos.",
        )

    def handle(self, *args, **options):
        owner = None
        owner_id = options.get("owner_id")
        if owner_id:
            owner = get_user_model().objects.filter(pk=owner_id).first()
            if owner is None:
                raise CommandError(f"Owner {owner_id} no encontrado.")

        metrics = get_schedule_run_operational_metrics(owner=owner)
        self.stdout.write(json.dumps(metrics, ensure_ascii=True, sort_keys=True))

        if options.get("fail_on_anomalies"):
            if metrics["conflicts_manual_vs_intent"] > 0 or metrics["templates_with_multiple_open_runs"] > 0:
                raise CommandError("Se detectaron anomalias operativas en scheduled_payments.")
