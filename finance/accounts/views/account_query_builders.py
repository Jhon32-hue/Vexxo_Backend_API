"""
Builders de query y payloads de lectura para `accounts`.

Descripcion general:
- encapsula filtros, agregaciones y respuestas operativas derivadas del modulo

Analisis detallado:
- separa el armado de querysets del viewset para mantener la capa HTTP simple
- aqui viven lecturas reutilizables como summary, sync overview y contrato de
  eventos
"""

from __future__ import annotations

from django.db.models import Count, Q, Sum

from finance.accounts.domain.events import (
    get_account_event_catalog,
    get_account_event_governance,
    get_account_event_runtime,
)
from finance.accounts.models import Account, AccountStatus
from finance.accounts.services.permission_service import account_scope_for_user


def is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "si"}


def is_false(value: str | None) -> bool:
    return (value or "").strip().lower() in {"0", "false", "no"}


def _base_account_queryset(*, user):
    return account_scope_for_user(
        user,
        Account.objects.select_related("owner", "shared_from_user").all(),
    )


def _annotate_account_counts(qs):
    return qs.annotate(
        total_transactions=Count("transactions", distinct=True),
        active_memberships_count=Count(
            "memberships",
            filter=Q(memberships__is_active=True),
            distinct=True,
        ),
    )


def _apply_account_filters(*, qs, user, query_params):

    account_type = query_params.get("type")
    currency = query_params.get("currency")
    ownership = query_params.get("ownership")
    role = query_params.get("role")
    visibility = query_params.get("visibility")
    status_param = query_params.get("status")
    provider = query_params.get("provider")
    institution = query_params.get("institution")
    sync_status = query_params.get("sync_status")
    sync_health = query_params.get("sync_health")
    external_link = query_params.get("external_link")
    primary_param = query_params.get("is_primary")
    search = query_params.get("search")
    mine_param = query_params.get("mine")
    shared_param = query_params.get("shared")
    active_param = query_params.get("active")
    archived_param = query_params.get("archived")
    include_closed = query_params.get("include_closed")
    order_by = query_params.get("order_by")

    if account_type:
        qs = qs.filter(type=account_type)
    if currency:
        qs = qs.filter(currency=currency)
    if ownership:
        qs = qs.filter(ownership=ownership)
    if role:
        qs = qs.filter(role=role)
    if visibility:
        qs = qs.filter(visibility=visibility)
    if provider:
        qs = qs.filter(provider=provider)
    if institution:
        qs = qs.filter(institution__icontains=institution)
    if sync_status:
        qs = qs.filter(sync_status=sync_status)
    if external_link is not None:
        if is_true(external_link):
            qs = qs.exclude(provider="").exclude(external_id="")
        elif is_false(external_link):
            qs = qs.filter(provider="", external_id="")
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(institution__icontains=search))

    if is_true(mine_param):
        qs = qs.filter(owner=user)
    elif is_true(shared_param):
        qs = qs.exclude(owner=user)

    if primary_param is not None:
        qs = qs.filter(is_primary=is_true(primary_param))

    if status_param:
        qs = qs.filter(status=status_param)
    elif active_param is not None:
        if is_true(active_param):
            qs = qs.filter(status=AccountStatus.ACTIVE)
        elif is_false(active_param):
            qs = qs.exclude(status=AccountStatus.ACTIVE)
    elif not is_true(include_closed):
        qs = qs.exclude(status=AccountStatus.CLOSED)

    if archived_param is not None:
        archived_filter = Q(status=AccountStatus.ARCHIVED) | Q(archived=True)
        if is_true(archived_param):
            qs = qs.filter(archived_filter)
        elif is_false(archived_param):
            qs = qs.exclude(archived_filter)

    if sync_health:
        health_filters = {
            "disconnected": Q(provider="") | Q(external_id=""),
            "error": Q(sync_status="error") & ~Q(provider="") & ~Q(external_id=""),
            "stale": Q(sync_status="stale") & ~Q(provider="") & ~Q(external_id=""),
            "syncing": Q(sync_status="running") & ~Q(provider="") & ~Q(external_id=""),
            "healthy": Q(sync_status="ok") & ~Q(provider="") & ~Q(external_id=""),
            "idle": Q(sync_status="idle") & ~Q(provider="") & ~Q(external_id=""),
        }
        if sync_health in health_filters:
            qs = qs.filter(health_filters[sync_health])

    allowed_order = {
        "created_at",
        "-created_at",
        "updated_at",
        "-updated_at",
        "name",
        "-name",
        "balance",
        "-balance",
    }
    qs = qs.distinct()
    if order_by in allowed_order:
        from security.query_safety import safe_order_by

        return safe_order_by(qs, order_by, allowed_fields=set(allowed_order))
    return qs.order_by("-created_at")


def build_account_list_queryset(*, user, query_params):
    qs = _base_account_queryset(user=user).prefetch_related("memberships__user", "memberships__invitations")
    qs = _annotate_account_counts(qs)
    return _apply_account_filters(qs=qs, user=user, query_params=query_params)


def build_account_detail_queryset(*, user, query_params):
    qs = _base_account_queryset(user=user).prefetch_related("memberships__user", "memberships__invitations")
    qs = _annotate_account_counts(qs)
    return _apply_account_filters(qs=qs, user=user, query_params=query_params)


def build_account_mutation_queryset(*, user, query_params):
    qs = _base_account_queryset(user=user)
    return _apply_account_filters(qs=qs, user=user, query_params=query_params)


def build_account_overview_queryset(*, user, query_params):
    qs = _annotate_account_counts(_base_account_queryset(user=user))
    return _apply_account_filters(qs=qs, user=user, query_params=query_params)


def build_account_members_queryset(*, account, query_params):
    memberships = account.memberships.select_related("user", "invited_by").prefetch_related("invitations").order_by(
        "-is_active", "user__username"
    )
    active_param = query_params.get("active")
    if active_param is not None:
        if is_true(active_param):
            memberships = memberships.filter(is_active=True)
        elif is_false(active_param):
            memberships = memberships.filter(is_active=False)
    return memberships


def build_summary_queryset(*, queryset):
    return queryset.values("type", "currency", "status").annotate(
        total_accounts=Count("id"),
        total_balance=Sum("balance"),
    )


def build_sync_overview_payload(*, queryset):
    with_external = queryset.exclude(provider="").exclude(external_id="")
    return list(
        with_external.values("sync_status", "provider").annotate(total_accounts=Count("id")).order_by("provider", "sync_status")
    )


def build_operational_overview_payload(*, queryset, user):
    with_external = queryset.exclude(provider="").exclude(external_id="")
    return {
        "totals": {
            "accounts": queryset.count(),
            "active": queryset.filter(status=AccountStatus.ACTIVE).count(),
            "closed": queryset.filter(status=AccountStatus.CLOSED).count(),
            "archived": queryset.filter(status=AccountStatus.ARCHIVED).count(),
            "frozen": queryset.filter(status=AccountStatus.FROZEN).count(),
            "linked_external": with_external.count(),
            "primary_accounts": queryset.filter(is_primary=True).count(),
            "shared_accounts": queryset.exclude(owner=user).count(),
        },
        "by_status": list(queryset.values("status").annotate(total=Count("id")).order_by("status")),
        "by_type": list(queryset.values("type").annotate(total=Count("id")).order_by("type")),
        "by_currency": list(
            queryset.values("currency").annotate(total=Count("id"), total_balance=Sum("balance")).order_by("currency")
        ),
        "by_sync_status": list(with_external.values("sync_status").annotate(total=Count("id")).order_by("sync_status")),
    }


def build_event_contract_payload():
    return {
        "module": "finance.accounts",
        "aggregate": "account",
        "runtime": get_account_event_runtime(),
        "governance": get_account_event_governance(),
        "events": get_account_event_catalog(),
    }
