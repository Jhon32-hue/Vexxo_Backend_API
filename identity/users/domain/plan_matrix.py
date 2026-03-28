"""
Politica canonica de planes para identidad.

Descripcion general:
- centraliza la matriz oficial de capacidades del producto por plan
- sirve como fuente compartida para `identity.users` y modulos que dependan de
  capacidades del usuario

Analisis detallado:
- `User.plan` es la fuente oficial del plan del usuario, pero la definicion de
  limites y capacidades no debe vivir duplicada en varios modulos
- esta matriz unifica reglas de cuentas, contactos, reportes, conexiones API y
  otros features que luego pueden ser consumidos por `accounts`, `transactions`
  o paneles administrativos
- los overrides del modelo `User` siguen aplicando por encima de esta base

Que se puede hacer despues:
- mover esta matriz a una app de billing/product catalog si Vexxo separa
  suscripcion y capacidades comerciales
- agregar reglas por region, tenant, beta flag o cohortes de growth
"""

from __future__ import annotations

from copy import deepcopy


PLAN_CAPABILITY_MATRIX = {
    "free": {
        "max_accounts": 3,
        "max_active_accounts": 3,
        "max_primary_accounts": 1,
        "max_investment_accounts": 1,
        "max_monthly_tx_per_account": 20,
        "max_monthly_reports": 1,
        "max_api_connections": 1,
        "max_shared_accounts": 2,
        "max_contacts": 2,
        "max_observed_accounts": 2,
        "max_groups": 2,
        "max_shared_goals": 2,
        "max_documents_per_month": 20,
    },
    "plus": {
        "max_accounts": 6,
        "max_active_accounts": 6,
        "max_primary_accounts": 3,
        "max_investment_accounts": 3,
        "max_monthly_tx_per_account": 500,
        "max_monthly_reports": 10,
        "max_api_connections": 5,
        "max_shared_accounts": 10,
        "max_contacts": 100,
        "max_observed_accounts": 10,
        "max_groups": 20,
        "max_shared_goals": 20,
        "max_documents_per_month": 500,
    },
    "pro": {
        "max_accounts": None,
        "max_active_accounts": None,
        "max_primary_accounts": None,
        "max_investment_accounts": None,
        "max_monthly_tx_per_account": None,
        "max_monthly_reports": None,
        "max_api_connections": None,
        "max_shared_accounts": None,
        "max_contacts": None,
        "max_observed_accounts": None,
        "max_groups": None,
        "max_shared_goals": None,
        "max_documents_per_month": None,
    },
    "enterprise": {
        "max_accounts": None,
        "max_active_accounts": None,
        "max_primary_accounts": None,
        "max_investment_accounts": None,
        "max_monthly_tx_per_account": None,
        "max_monthly_reports": None,
        "max_api_connections": None,
        "max_shared_accounts": None,
        "max_contacts": None,
        "max_observed_accounts": None,
        "max_groups": None,
        "max_shared_goals": None,
        "max_documents_per_month": None,
    },
}


def resolve_plan_code(plan: str | None) -> str:
    return str(plan or "free").strip().lower() or "free"


def get_plan_capabilities(plan: str | None) -> dict:
    plan_code = resolve_plan_code(plan)
    capabilities = PLAN_CAPABILITY_MATRIX.get(plan_code, PLAN_CAPABILITY_MATRIX["free"])
    return {
        "plan": plan_code,
        **deepcopy(capabilities),
    }
