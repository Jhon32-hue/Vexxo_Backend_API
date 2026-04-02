"""
Limites operativos internos por proveedor y rail.

Se resuelven desde configuracion para que Vexxo no quede acoplado a un
proveedor concreto ni a caps hardcodeados en el codigo. Si no hay configuracion
explicita, el sistema no aplica caps operativos por defecto.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings

ZERO = Decimal("0.00")


def _platform_limits_config() -> dict:
    return dict(getattr(settings, "PAYMENTS_PLATFORM_LIMITS", {}) or {})


def _resolve_scope(provider: str, scope: str, rail: str) -> dict:
    platform_provider_limits = _platform_limits_config()
    provider_key = str(provider or "").strip().lower() or "default"
    rail_key = str(rail or "").strip().lower() or "default"
    provider_cfg = platform_provider_limits.get(provider_key, platform_provider_limits.get("default", {}))
    scope_cfg = provider_cfg.get(scope, {})
    selected = scope_cfg.get(rail_key) or scope_cfg.get("default")
    if selected:
        return selected
    default_scope_cfg = platform_provider_limits.get("default", {}).get(scope, {})
    return default_scope_cfg.get(rail_key) or default_scope_cfg.get("default") or {}


def resolve_payment_platform_limits(*, provider: str, rail: str) -> dict:
    selected = _resolve_scope(provider, "payments", rail)
    return {
        "provider": str(provider or "").strip().lower() or "default",
        "rail": str(rail or "").strip().lower() or "default",
        "single_cap": Decimal(str(selected.get("single_cap"))) if selected.get("single_cap") not in (None, "") else None,
        "daily_cap": Decimal(str(selected.get("daily_cap"))) if selected.get("daily_cap") not in (None, "") else None,
    }


def resolve_payout_platform_limits(*, provider: str, rail: str) -> dict:
    selected = _resolve_scope(provider, "payouts", rail)
    return {
        "provider": str(provider or "").strip().lower() or "default",
        "rail": str(rail or "").strip().lower() or "default",
        "single_cap": Decimal(str(selected.get("single_cap"))) if selected.get("single_cap") not in (None, "") else None,
        "daily_cap": Decimal(str(selected.get("daily_cap"))) if selected.get("daily_cap") not in (None, "") else None,
    }
