"""
Politica operativa de snapshots de balance para accounts.

Descripcion general:
- centraliza frecuencia declarada, retention y cleanup de `BalanceSnapshot`
- evita que la politica de reconciliacion quede dispersa entre comandos, vistas
  y jobs futuros

Analisis detallado:
- `BalanceSnapshot` es valioso para soporte y observabilidad, pero puede crecer
  muy rapido si no tiene reglas de retencion
- esta capa define cuanto tiempo se conserva cada tipo de snapshot y ofrece un
  cleanup reutilizable por management command o job programado
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max
from django.utils import timezone

from finance.accounts.models import BalanceSnapshot


@dataclass(frozen=True)
class BalanceSnapshotPolicy:
    scheduled_frequency: str
    retention_days: int
    inconsistent_retention_days: int
    on_demand_retention_days: int
    auto_repair_retention_days: int
    max_per_account: int


def get_balance_snapshot_policy() -> BalanceSnapshotPolicy:
    return BalanceSnapshotPolicy(
        scheduled_frequency=getattr(settings, "ACCOUNTS_BALANCE_SNAPSHOT_SCHEDULED_FREQUENCY", "nightly"),
        retention_days=max(1, int(getattr(settings, "ACCOUNTS_BALANCE_SNAPSHOT_RETENTION_DAYS", 90))),
        inconsistent_retention_days=max(
            1, int(getattr(settings, "ACCOUNTS_BALANCE_SNAPSHOT_INCONSISTENT_RETENTION_DAYS", 365))
        ),
        on_demand_retention_days=max(
            1, int(getattr(settings, "ACCOUNTS_BALANCE_SNAPSHOT_ON_DEMAND_RETENTION_DAYS", 180))
        ),
        auto_repair_retention_days=max(
            1, int(getattr(settings, "ACCOUNTS_BALANCE_SNAPSHOT_AUTO_REPAIR_RETENTION_DAYS", 365))
        ),
        max_per_account=max(10, int(getattr(settings, "ACCOUNTS_BALANCE_SNAPSHOT_MAX_PER_ACCOUNT", 200))),
    )


def get_balance_snapshot_policy_summary() -> dict:
    policy = get_balance_snapshot_policy()
    return {
        "scheduled_frequency": policy.scheduled_frequency,
        "retention_days": policy.retention_days,
        "inconsistent_retention_days": policy.inconsistent_retention_days,
        "on_demand_retention_days": policy.on_demand_retention_days,
        "auto_repair_retention_days": policy.auto_repair_retention_days,
        "max_per_account": policy.max_per_account,
        "sources": {
            "scheduled_job": "snapshot programado por job o reconciliacion recurrente",
            "manual_recheck": "snapshot manual u operacion de soporte",
            "on_demand": "snapshot bajo demanda por API o diagnostico",
            "post_incident": "snapshot posterior a un incidente o drift relevante",
        },
    }


def cleanup_balance_snapshots(*, dry_run: bool = True, account_id: int | None = None, limit: int = 5000) -> dict:
    policy = get_balance_snapshot_policy()
    now = timezone.now()

    general_cutoff = now - timedelta(days=policy.retention_days)
    inconsistent_cutoff = now - timedelta(days=policy.inconsistent_retention_days)
    on_demand_cutoff = now - timedelta(days=policy.on_demand_retention_days)
    auto_repair_cutoff = now - timedelta(days=policy.auto_repair_retention_days)

    qs = BalanceSnapshot.objects.all().order_by("account_id", "-as_of", "-created_at")
    if account_id:
        qs = qs.filter(account_id=account_id)

    grouped_latest = (
        qs.values("account_id")
        .annotate(latest_as_of=Max("as_of"))
        .order_by()
    )
    keep_latest_ids: list[int] = []
    for row in grouped_latest:
        latest_id = (
            qs.filter(account_id=row["account_id"], as_of=row["latest_as_of"])
            .values_list("id", flat=True)
            .first()
        )
        if latest_id:
            keep_latest_ids.append(int(latest_id))

    candidates = qs.exclude(id__in=keep_latest_ids)

    general_candidates = candidates.filter(is_consistent=True, source="scheduled_job", created_at__lt=general_cutoff)
    on_demand_candidates = candidates.filter(
        source__in=["manual_recheck", "on_demand"],
        created_at__lt=on_demand_cutoff,
    )
    inconsistent_candidates = candidates.filter(is_consistent=False, created_at__lt=inconsistent_cutoff)
    auto_repair_candidates = candidates.filter(note="auto_repaired", created_at__lt=auto_repair_cutoff)

    candidate_ids = set(general_candidates.values_list("id", flat=True)[:limit])
    candidate_ids.update(on_demand_candidates.values_list("id", flat=True)[:limit])
    candidate_ids.update(inconsistent_candidates.values_list("id", flat=True)[:limit])
    candidate_ids.update(auto_repair_candidates.values_list("id", flat=True)[:limit])

    oversized_accounts = (
        qs.values("account_id")
        .annotate(total=Count("id"))
        .filter(total__gt=policy.max_per_account)
        .order_by()
    )
    for row in oversized_accounts:
        overflow = int(row["total"]) - policy.max_per_account
        if overflow <= 0:
            continue
        overflow_ids = list(
            qs.filter(account_id=row["account_id"])
            .order_by("-as_of", "-created_at")
            .values_list("id", flat=True)[policy.max_per_account : policy.max_per_account + overflow]
        )
        candidate_ids.update(int(value) for value in overflow_ids)

    delete_qs = BalanceSnapshot.objects.filter(id__in=candidate_ids)
    summary = {
        "dry_run": dry_run,
        "total_candidates": delete_qs.count(),
        "by_source": list(delete_qs.values("source").annotate(total=Count("id")).order_by("source")),
        "policy": get_balance_snapshot_policy_summary(),
    }
    if not dry_run and candidate_ids:
        deleted_count, _ = delete_qs.delete()
        summary["deleted"] = deleted_count
    return summary
