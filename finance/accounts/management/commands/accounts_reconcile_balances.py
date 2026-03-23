from __future__ import annotations

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from finance.accounts.models.account import Account
from finance.accounts.services.reconcile_service import create_balance_snapshot


class Command(BaseCommand):
    help = "Recalcula y compara balances (cache vs ledger). Crea BalanceSnapshot y opcionalmente repara drift."

    def add_arguments(self, parser):
        parser.add_argument("--owner-id", type=int, default=0, help="Solo reconciliar cuentas de un owner_id")
        parser.add_argument("--account-id", type=int, default=0, help="Solo reconciliar una cuenta específica")
        parser.add_argument("--include-archived", action="store_true")
        parser.add_argument("--include-inactive", action="store_true")
        parser.add_argument("--drift-threshold", type=str, default="0.000001")
        parser.add_argument("--auto-repair", action="store_true", help="Si drift supera threshold, repara cache con recalc.")
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        owner_id = int(opts["owner_id"] or 0)
        account_id = int(opts["account_id"] or 0)
        include_archived = bool(opts["include_archived"])
        include_inactive = bool(opts["include_inactive"])
        drift_threshold = Decimal(str(opts["drift_threshold"]))
        auto_repair = bool(opts["auto_repair"])
        limit = int(opts["limit"])
        dry_run = bool(opts["dry_run"])

        qs = Account.objects.all()

        if owner_id:
            qs = qs.filter(owner_id=owner_id)

        if account_id:
            qs = qs.filter(pk=account_id)

        if not include_archived:
            qs = qs.filter(archived=False)

        if not include_inactive:
            qs = qs.filter(is_active=True)

        # evita cuentas cerradas si tienes close logic
        qs = qs.filter(Q(closed_at__isnull=True) | Q(is_active=True))

        qs = qs.order_by("pk")[:limit]

        as_of = timezone.now()

        total = 0
        inconsistent = 0
        repaired = 0

        for acc in qs:
            total += 1

            if dry_run:
                cached = acc.balance
                recomputed = acc.current_balance()
                drift = Decimal(recomputed) - Decimal(cached)
                status = "OK" if abs(drift) <= drift_threshold else "DRIFT"
                self.stdout.write(
                    f"[dry-run] acc={acc.pk} owner={acc.owner_id} cached={cached} recomputed={recomputed} drift={drift} {status}"
                )
                continue

            snap = create_balance_snapshot(
                account=acc,
                as_of=as_of,
                drift_threshold=drift_threshold,
                auto_repair=auto_repair,
            )

            if abs(Decimal(snap.drift)) > drift_threshold:
                inconsistent += 1
                if auto_repair:
                    repaired += 1

            self.stdout.write(
                f"[reconcile] acc={acc.pk} cached={snap.balance_cached} recomputed={snap.balance_recomputed} drift={snap.drift} consistent={snap.is_consistent}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"[reconcile] done total={total} inconsistent={inconsistent} repaired={repaired} dry_run={dry_run}"
            )
        )
