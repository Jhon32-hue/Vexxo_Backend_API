"""
Comando operativo para cleanup de snapshots de balance.

Descripcion general:
- aplica la politica de retencion de `BalanceSnapshot`
- permite dry-run, foco por cuenta y consulta de la politica activa

Analisis detallado:
- este comando sirve para jobs nocturnos, mantenimiento o soporte
- evita que los snapshots crezcan sin control mientras conserva evidencia
  relevante para drift, auto-repair y revisiones manuales
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from finance.accounts.services.snapshot_policy_service import cleanup_balance_snapshots, get_balance_snapshot_policy_summary


class Command(BaseCommand):
    help = "Limpia snapshots antiguos de balances segun la politica operativa del modulo accounts."

    def add_arguments(self, parser):
        parser.add_argument("--account-id", type=int, default=0, help="Limpiar solo snapshots de una cuenta.")
        parser.add_argument("--limit", type=int, default=5000, help="Maximo de snapshots candidatos por corrida.")
        parser.add_argument("--dry-run", action="store_true", help="No borra, solo reporta candidatos.")
        parser.add_argument("--show-policy", action="store_true", help="Muestra la politica y termina.")

    def handle(self, *args, **opts):
        if opts["show_policy"]:
            self.stdout.write(str(get_balance_snapshot_policy_summary()))
            return

        result = cleanup_balance_snapshots(
            dry_run=bool(opts["dry_run"]),
            account_id=int(opts["account_id"] or 0) or None,
            limit=int(opts["limit"]),
        )
        self.stdout.write(str(result))
