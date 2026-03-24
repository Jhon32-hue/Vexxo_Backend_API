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

Que se puede hacer despues:
- mover aqui limites mas finos por region, tenant o features beta
- agregar guardas de sincronizacion externa, documentos o cuentas observadas
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from finance.accounts.models.account import Account, AccountStatus, AccountType

User = get_user_model()


ACCOUNT_PLAN_MATRIX = {
    "free": {
        "max_active_accounts": 3,
        "max_primary_accounts": 1,
        "max_investment_accounts": 1,
    },
    "plus": {
        "max_active_accounts": 6,
        "max_primary_accounts": 3,
        "max_investment_accounts": 3,
    },
    "pro": {
        "max_active_accounts": None,
        "max_primary_accounts": None,
        "max_investment_accounts": None,
    },
    "enterprise": {
        "max_active_accounts": None,
        "max_primary_accounts": None,
        "max_investment_accounts": None,
    },
}

INVESTMENT_TYPES = {
    AccountType.INVESTMENT,
    AccountType.BROKERAGE,
    AccountType.CRYPTO,
    AccountType.RETIREMENT,
}


def resolve_account_plan(user: User) -> str:
    settings_plan = getattr(getattr(user, "settings", None), "plan", None)
    explicit_plan = settings_plan or getattr(user, "plan", None) or "free"
    return str(explicit_plan).lower()


def get_account_plan_limits(user: User) -> dict:
    plan = resolve_account_plan(user)
    limits = dict(ACCOUNT_PLAN_MATRIX.get(plan, ACCOUNT_PLAN_MATRIX["free"]))

    if getattr(user, "max_accounts_override", None) is not None:
        limits["max_active_accounts"] = user.max_accounts_override

    return {
        "plan": plan,
        **limits,
    }


def get_account_plan_usage(user: User, *, exclude_account_id=None) -> dict:
    base_qs = Account.objects.filter(owner=user, status=AccountStatus.ACTIVE)
    if exclude_account_id:
        base_qs = base_qs.exclude(pk=exclude_account_id)

    active_accounts = base_qs.count()
    active_primary_accounts = base_qs.filter(is_primary=True).count()
    active_investment_accounts = base_qs.filter(type__in=INVESTMENT_TYPES).count()

    return {
        "active_accounts": active_accounts,
        "active_primary_accounts": active_primary_accounts,
        "active_investment_accounts": active_investment_accounts,
    }


def account_creation_limit_errors(user: User, *, account_type: str) -> dict:
    limits = get_account_plan_limits(user)
    usage = get_account_plan_usage(user)
    errors = {}

    max_active = limits.get("max_active_accounts")
    if max_active is not None and usage["active_accounts"] >= max_active:
        errors["plan"] = (
            f"Tu plan {limits['plan']} permite hasta {max_active} cuentas activas."
        )

    max_investment = limits.get("max_investment_accounts")
    if (
        account_type in INVESTMENT_TYPES
        and max_investment is not None
        and usage["active_investment_accounts"] >= max_investment
    ):
        errors["type"] = (
            f"Tu plan {limits['plan']} permite hasta {max_investment} cuentas de inversion."
        )

    return errors


def primary_account_limit_errors(user: User, *, exclude_account_id=None) -> dict:
    limits = get_account_plan_limits(user)
    usage = get_account_plan_usage(user, exclude_account_id=exclude_account_id)
    max_primary = limits.get("max_primary_accounts")

    if max_primary is not None and usage["active_primary_accounts"] >= max_primary:
        return {
            "is_primary": (
                f"Tu plan {limits['plan']} permite hasta {max_primary} cuentas principales activas."
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
