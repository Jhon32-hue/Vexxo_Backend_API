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
        "max_accounts": None,
        "max_active_accounts": None,
        "max_manual_accounts": None,
        "max_connected_accounts": 1,
        "max_primary_accounts": 1,
        "max_investment_accounts": 1,
        "max_monthly_tx_per_account": None,
        "max_monthly_reports": 1,
        "max_api_connections": 1,
        "max_shared_accounts": 2,
        "max_members_per_account": 2,
        "max_contacts": 10,
        "max_observed_accounts": 2,
        "max_groups": 2,
        "max_shared_goals": 2,
        "max_documents_per_month": 10,
        "max_rules": 1,
        "ai_requests_per_month": 20,
        "insights_level": "basic",
        "smart_alerts_enabled": False,
        "embedded_payments_enabled": True,
        "payouts_enabled": False,
        "max_scheduled_payments": 3,
        "max_payments_per_month": 10,
        "max_daily_payment_volume": "200000.00",
        "max_monthly_payment_volume": "500000.00",
        "max_single_payment_amount": "150000.00",
        "max_payouts_per_month": 0,
        "max_payout_amount": "0.00",
        "max_daily_payout_volume": "0.00",
        "max_monthly_payout_volume": "0.00",
        "payment_fee_percentage": "0.0149",
        "payment_fee_flat": "900.00",
        "payment_fee_vat_rate": "0.19",
        "payout_fee_percentage": "0.0000",
        "payout_fee_flat": "0.00",
        "payout_fee_vat_rate": "0.19",
        "ads_enabled": True,
    },
    "pro": {
        "max_accounts": None,
        "max_active_accounts": None,
        "max_manual_accounts": None,
        "max_connected_accounts": None,
        "max_primary_accounts": None,
        "max_investment_accounts": None,
        "max_monthly_tx_per_account": None,
        "max_monthly_reports": None,
        "max_api_connections": None,
        "max_shared_accounts": None,
        "max_members_per_account": None,
        "max_contacts": None,
        "max_observed_accounts": None,
        "max_groups": None,
        "max_shared_goals": None,
        "max_documents_per_month": 100,
        "max_rules": None,
        "ai_requests_per_month": 500,
        "insights_level": "advanced",
        "smart_alerts_enabled": True,
        "embedded_payments_enabled": True,
        "payouts_enabled": True,
        "max_scheduled_payments": None,
        "max_payments_per_month": None,
        "max_daily_payment_volume": "3000000.00",
        "max_monthly_payment_volume": None,
        "max_single_payment_amount": "1500000.00",
        "max_payouts_per_month": 10,
        "max_payout_amount": "5000000.00",
        "max_daily_payout_volume": "10000000.00",
        "max_monthly_payout_volume": "20000000.00",
        "payment_fee_percentage": "0.0079",
        "payment_fee_flat": "500.00",
        "payment_fee_vat_rate": "0.19",
        "payout_fee_percentage": "0.0000",
        "payout_fee_flat": "700.00",
        "payout_fee_vat_rate": "0.19",
        "ads_enabled": False,
    },
    "enterprise": {
        "max_accounts": None,
        "max_active_accounts": None,
        "max_manual_accounts": None,
        "max_connected_accounts": None,
        "max_primary_accounts": None,
        "max_investment_accounts": None,
        "max_monthly_tx_per_account": None,
        "max_monthly_reports": None,
        "max_api_connections": None,
        "max_shared_accounts": None,
        "max_members_per_account": None,
        "max_contacts": None,
        "max_observed_accounts": None,
        "max_groups": None,
        "max_shared_goals": None,
        "max_documents_per_month": None,
        "max_rules": None,
        "ai_requests_per_month": None,
        "insights_level": "enterprise",
        "smart_alerts_enabled": True,
        "embedded_payments_enabled": True,
        "payouts_enabled": True,
        "max_scheduled_payments": None,
        "max_payments_per_month": None,
        "max_daily_payment_volume": None,
        "max_monthly_payment_volume": None,
        "max_single_payment_amount": None,
        "max_payouts_per_month": None,
        "max_payout_amount": None,
        "max_daily_payout_volume": None,
        "max_monthly_payout_volume": None,
        "payment_fee_percentage": "0.0050",
        "payment_fee_flat": "0.00",
        "payment_fee_vat_rate": "0.19",
        "payout_fee_percentage": "0.0000",
        "payout_fee_flat": "0.00",
        "payout_fee_vat_rate": "0.19",
        "ads_enabled": False,
    },
}


def resolve_plan_code(plan: str | None) -> str:
    normalized = str(plan or "free").strip().lower() or "free"
    if normalized == "plus":
        return "pro"
    return normalized


def get_plan_capabilities(plan: str | None) -> dict:
    plan_code = resolve_plan_code(plan)
    capabilities = PLAN_CAPABILITY_MATRIX.get(plan_code, PLAN_CAPABILITY_MATRIX["free"])
    return {
        "plan": plan_code,
        **deepcopy(capabilities),
    }
