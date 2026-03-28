"""
Guardas de dominio para cuentas financieras.

Descripcion general:
- encapsula limites de plan, uso actual y reglas previas a operaciones de
  creacion o asignacion de cuenta principal

Analisis detallado:
- aunque el usuario tenga una matriz de plan global, `accounts` necesita sus
  propias reglas operativas porque el producto puede evolucionar por modulo
- estas guardas se apoyan en la data real del owner y no dependen de que el
  frontend recuerde limites o planes
- sirven tanto para serializadores como para viewsets y jobs internos
- `user.plan` se considera la fuente oficial para el modulo; `user.settings.plan`
  queda como compatibilidad temporal si el campo canonico aun no esta poblado

Que se puede hacer despues:
- mover aqui limites mas finos por region, tenant o features beta
- agregar guardas de sincronizacion externa, documentos o cuentas observadas
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from finance.accounts.models.account import Account, AccountStatus, AccountType
from identity.users.domain.plan_matrix import get_plan_capabilities

User = get_user_model()

INVESTMENT_TYPES = {
    AccountType.INVESTMENT,
    AccountType.BROKERAGE,
    AccountType.CRYPTO,
    AccountType.RETIREMENT,
}

COUNTED_PLAN_STATUSES = {
    AccountStatus.ACTIVE,
    AccountStatus.FROZEN,
}

PRIMARY_COUNTED_STATUSES = {
    AccountStatus.ACTIVE,
}


def _limit_error(*, message: str, limit, current, plan: str) -> dict:
    return {
        "message": message,
        "limit": limit,
        "current": current,
        "plan": plan,
    }


def resolve_account_plan(user: User) -> str:
    canonical_plan = getattr(user, "plan", None)
    compatibility_plan = getattr(getattr(user, "settings", None), "plan", None)
    resolved = canonical_plan or compatibility_plan or "free"
    return str(resolved).lower()


def get_account_plan_limits(user: User) -> dict:
    plan = resolve_account_plan(user)
    capability_snapshot = get_plan_capabilities(plan)
    limits = {
        "max_active_accounts": capability_snapshot.get("max_active_accounts"),
        "max_primary_accounts": capability_snapshot.get("max_primary_accounts"),
        "max_investment_accounts": capability_snapshot.get("max_investment_accounts"),
    }

    if getattr(user, "max_accounts_override", None) is not None:
        limits["max_active_accounts"] = user.max_accounts_override

    return {
        "plan": plan,
        **limits,
    }


def get_account_plan_usage(user: User, *, exclude_account_id=None) -> dict:
    base_qs = Account.objects.filter(owner=user, status__in=COUNTED_PLAN_STATUSES)
    if exclude_account_id:
        base_qs = base_qs.exclude(pk=exclude_account_id)

    primary_qs = base_qs.filter(status__in=PRIMARY_COUNTED_STATUSES)

    active_accounts = base_qs.count()
    active_primary_accounts = primary_qs.filter(is_primary=True).count()
    active_investment_accounts = base_qs.filter(type__in=INVESTMENT_TYPES).count()

    return {
        "active_accounts": active_accounts,
        "active_primary_accounts": active_primary_accounts,
        "active_investment_accounts": active_investment_accounts,
        "counted_statuses": sorted(COUNTED_PLAN_STATUSES),
        "primary_counted_statuses": sorted(PRIMARY_COUNTED_STATUSES),
    }


def account_creation_limit_errors(user: User, *, account_type: str) -> dict:
    limits = get_account_plan_limits(user)
    usage = get_account_plan_usage(user)
    errors = {}

    max_active = limits.get("max_active_accounts")
    if max_active is not None and usage["active_accounts"] >= max_active:
        errors["plan"] = _limit_error(
            message=f"Tu plan {limits['plan']} permite hasta {max_active} cuentas activas o congeladas.",
            limit=max_active,
            current=usage["active_accounts"],
            plan=limits["plan"],
        )

    max_investment = limits.get("max_investment_accounts")
    if (
        account_type in INVESTMENT_TYPES
        and max_investment is not None
        and usage["active_investment_accounts"] >= max_investment
    ):
        errors["type"] = _limit_error(
            message=f"Tu plan {limits['plan']} permite hasta {max_investment} cuentas de inversion.",
            limit=max_investment,
            current=usage["active_investment_accounts"],
            plan=limits["plan"],
        )

    return errors


def primary_account_limit_errors(user: User, *, exclude_account_id=None) -> dict:
    limits = get_account_plan_limits(user)
    usage = get_account_plan_usage(user, exclude_account_id=exclude_account_id)
    max_primary = limits.get("max_primary_accounts")

    if max_primary is not None and usage["active_primary_accounts"] >= max_primary:
        return {
            "is_primary": _limit_error(
                message=f"Tu plan {limits['plan']} permite hasta {max_primary} cuentas principales activas.",
                limit=max_primary,
                current=usage["active_primary_accounts"],
                plan=limits["plan"],
            )
        }
    return {}


def get_account_plan_snapshot(user: User, *, exclude_account_id=None) -> dict:
    limits = get_account_plan_limits(user)
    usage = get_account_plan_usage(user, exclude_account_id=exclude_account_id)
    return {
        "plan": limits["plan"],
        "limits": {
            "max_active_accounts": limits["max_active_accounts"],
            "max_primary_accounts": limits["max_primary_accounts"],
            "max_investment_accounts": limits["max_investment_accounts"],
        },
        "usage": usage,
    }
