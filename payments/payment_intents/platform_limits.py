"""
Limites operativos internos por proveedor y rail.

Estos caps no representan pricing ni entitlements comerciales. Representan
proteccion operativa de Vexxo:

- exposicion diaria por rail/proveedor
- monto maximo por instruccion
- margen de seguridad por fraude, conciliacion o soporte

Se aplican aunque el PSP soporte mas volumen.
"""

from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0.00")

DEFAULT_PAYMENT_LIMITS = {
    "single_cap": Decimal("10000000.00"),
    "daily_cap": Decimal("20000000.00"),
}

DEFAULT_PAYOUT_LIMITS = {
    "single_cap": Decimal("10000000.00"),
    "daily_cap": Decimal("30000000.00"),
}


PLATFORM_PROVIDER_LIMITS = {
    "default": {
        "payments": {
            "default": dict(DEFAULT_PAYMENT_LIMITS),
        },
        "payouts": {
            "default": dict(DEFAULT_PAYOUT_LIMITS),
        },
    },
    "wompi": {
        "payments": {
            "default": {
                "single_cap": Decimal("5000000.00"),
                "daily_cap": Decimal("15000000.00"),
            },
            "pse": {
                "single_cap": Decimal("5000000.00"),
                "daily_cap": Decimal("15000000.00"),
            },
            "bank_transfer": {
                "single_cap": Decimal("8000000.00"),
                "daily_cap": Decimal("18000000.00"),
            },
        },
        "payouts": {
            "default": {
                "single_cap": Decimal("8000000.00"),
                "daily_cap": Decimal("25000000.00"),
            },
            "payout": {
                "single_cap": Decimal("8000000.00"),
                "daily_cap": Decimal("25000000.00"),
            },
            "bank_transfer": {
                "single_cap": Decimal("8000000.00"),
                "daily_cap": Decimal("25000000.00"),
            },
        },
    },
}


def _resolve_scope(provider: str, scope: str, rail: str) -> dict:
    provider_key = str(provider or "").strip().lower() or "default"
    rail_key = str(rail or "").strip().lower() or "default"
    provider_cfg = PLATFORM_PROVIDER_LIMITS.get(provider_key, PLATFORM_PROVIDER_LIMITS["default"])
    scope_cfg = provider_cfg.get(scope, {})
    selected = scope_cfg.get(rail_key) or scope_cfg.get("default")
    if selected:
        return selected
    default_scope_cfg = PLATFORM_PROVIDER_LIMITS["default"].get(scope, {})
    return default_scope_cfg.get(rail_key) or default_scope_cfg.get("default") or {
        "single_cap": ZERO,
        "daily_cap": ZERO,
    }


def resolve_payment_platform_limits(*, provider: str, rail: str) -> dict:
    selected = _resolve_scope(provider, "payments", rail)
    return {
        "provider": str(provider or "").strip().lower() or "default",
        "rail": str(rail or "").strip().lower() or "default",
        "single_cap": Decimal(str(selected.get("single_cap") or ZERO)),
        "daily_cap": Decimal(str(selected.get("daily_cap") or ZERO)),
    }


def resolve_payout_platform_limits(*, provider: str, rail: str) -> dict:
    selected = _resolve_scope(provider, "payouts", rail)
    return {
        "provider": str(provider or "").strip().lower() or "default",
        "rail": str(rail or "").strip().lower() or "default",
        "single_cap": Decimal(str(selected.get("single_cap") or ZERO)),
        "daily_cap": Decimal(str(selected.get("daily_cap") or ZERO)),
    }
