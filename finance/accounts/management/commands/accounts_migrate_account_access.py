"""
Comando operativo para migrar `AccountAccess` hacia `AccountMembership`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from finance.accounts.services.account_access_migration_service import migrate_account_access_entries


class Command(BaseCommand):
    help = "Migra accesos legacy AccountAccess hacia AccountMembership."

    def add_arguments(self, parser):
        parser.add_argument("--account-id", type=int, default=0, help="Migrar solo un account_id.")
        parser.add_argument("--dry-run", action="store_true", help="No escribe cambios, solo resume.")
        parser.add_argument(
            "--deactivate-legacy",
            action="store_true",
            help="Desactiva los registros legacy luego de migrarlos.",
        )

    def handle(self, *args, **opts):
        result = migrate_account_access_entries(
            account_id=int(opts["account_id"] or 0) or None,
            dry_run=bool(opts["dry_run"]),
            deactivate_legacy=bool(opts["deactivate_legacy"]),
        )
        self.stdout.write(str(result))
