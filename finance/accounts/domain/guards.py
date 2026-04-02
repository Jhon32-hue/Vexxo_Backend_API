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

from finance.accounts.services.account_policy_service import (
    account_creation_limit_errors as policy_account_creation_limit_errors,
    get_account_plan_limits as policy_get_account_plan_limits,
    get_account_plan_snapshot as policy_get_account_plan_snapshot,
    get_account_plan_usage as policy_get_account_plan_usage,
    primary_account_limit_errors as policy_primary_account_limit_errors,
    resolve_account_plan as policy_resolve_account_plan,
)

User = get_user_model()


def resolve_account_plan(user: User) -> str:
    return policy_resolve_account_plan(user)


def get_account_plan_limits(user: User) -> dict:
    return policy_get_account_plan_limits(user)


def get_account_plan_usage(user: User, *, exclude_account_id=None) -> dict:
    return policy_get_account_plan_usage(user, exclude_account_id=exclude_account_id)


def account_creation_limit_errors(user: User, *, account_type: str) -> dict:
    return policy_account_creation_limit_errors(user, account_type=account_type)


def primary_account_limit_errors(user: User, *, exclude_account_id=None) -> dict:
    return policy_primary_account_limit_errors(user, exclude_account_id=exclude_account_id)


def get_account_plan_snapshot(user: User, *, exclude_account_id=None) -> dict:
    return policy_get_account_plan_snapshot(user, exclude_account_id=exclude_account_id)
