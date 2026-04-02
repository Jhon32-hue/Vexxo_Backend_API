"""
Resolver central de pricing para pagos embebidos y dispersiones.

La idea es separar:
- costo del proveedor
- impuestos del costo
- fee de Vexxo
- impuestos del fee de Vexxo

Asi se puede estimar antes del pago y comparar con el costo real despues del
callback del proveedor.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from identity.users.services.product_access_service import capabilities_for_user

ZERO = Decimal("0.00")
COP_QUANT = Decimal("0.01")

DEFAULT_PROVIDER_PRICING = {
    "wompi": {
        "percentage": Decimal("0.0265"),
        "flat": Decimal("700.00"),
        "vat_rate": Decimal("0.19"),
    },
    "generic": {
        "percentage": Decimal("0.0000"),
        "flat": Decimal("0.00"),
        "vat_rate": Decimal("0.19"),
    },
}


def _money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(COP_QUANT, rounding=ROUND_HALF_UP)


def _rate(value) -> Decimal:
    return Decimal(str(value or "0"))


def _provider_profile(provider: str, provider_pricing: dict | None = None) -> dict:
    if provider_pricing:
        return {
            "percentage": _rate(provider_pricing.get("percentage")),
            "flat": _money(provider_pricing.get("flat")),
            "vat_rate": _rate(provider_pricing.get("vat_rate", "0.19")),
        }
    code = str(provider or "").strip().lower()
    selected = DEFAULT_PROVIDER_PRICING.get(code, DEFAULT_PROVIDER_PRICING["generic"])
    return {
        "percentage": _rate(selected["percentage"]),
        "flat": _money(selected["flat"]),
        "vat_rate": _rate(selected["vat_rate"]),
    }


def calculate_embedded_payment_pricing(
    *,
    user,
    amount,
    provider: str,
    rail: str,
    country: str = "CO",
    payment_type: str = "other",
    provider_pricing: dict | None = None,
) -> dict:
    amount_value = _money(amount)
    capabilities = capabilities_for_user(user)
    provider_profile = _provider_profile(provider, provider_pricing=provider_pricing)

    provider_fee = _money((amount_value * provider_profile["percentage"]) + provider_profile["flat"])
    provider_tax = _money(provider_fee * provider_profile["vat_rate"])

    vexxo_fee = _money(
        (amount_value * _rate(capabilities.get("payment_fee_percentage", "0")))
        + _money(capabilities.get("payment_fee_flat", "0"))
    )
    vexxo_tax = _money(vexxo_fee * _rate(capabilities.get("payment_fee_vat_rate", "0.19")))

    total_fee = _money(provider_fee + provider_tax + vexxo_fee + vexxo_tax)
    total_charge = _money(amount_value + total_fee)

    return {
        "country": str(country or "CO").upper(),
        "provider": str(provider or "").strip(),
        "rail": str(rail or "").strip(),
        "payment_type": str(payment_type or "").strip(),
        "plan": capabilities.get("plan"),
        "amount": str(amount_value),
        "provider_cost": str(provider_fee),
        "provider_tax": str(provider_tax),
        "vexxo_fee": str(vexxo_fee),
        "vexxo_tax": str(vexxo_tax),
        "tax_cost": str(_money(provider_tax + vexxo_tax)),
        "total_fee": str(total_fee),
        "total_charge": str(total_charge),
        "breakdown": {
            "provider": {
                "percentage": str(provider_profile["percentage"]),
                "flat": str(provider_profile["flat"]),
                "vat_rate": str(provider_profile["vat_rate"]),
                "fee": str(provider_fee),
                "tax": str(provider_tax),
            },
            "vexxo": {
                "percentage": str(_rate(capabilities.get("payment_fee_percentage", "0"))),
                "flat": str(_money(capabilities.get("payment_fee_flat", "0"))),
                "vat_rate": str(_rate(capabilities.get("payment_fee_vat_rate", "0.19"))),
                "fee": str(vexxo_fee),
                "tax": str(vexxo_tax),
            },
        },
    }


def calculate_payout_pricing(
    *,
    user,
    amount,
    provider: str,
    rail: str,
    country: str = "CO",
    provider_pricing: dict | None = None,
) -> dict:
    amount_value = _money(amount)
    capabilities = capabilities_for_user(user)
    provider_profile = _provider_profile(provider, provider_pricing=provider_pricing)

    provider_fee = _money((amount_value * provider_profile["percentage"]) + provider_profile["flat"])
    provider_tax = _money(provider_fee * provider_profile["vat_rate"])

    vexxo_fee = _money(
        (amount_value * _rate(capabilities.get("payout_fee_percentage", "0")))
        + _money(capabilities.get("payout_fee_flat", "0"))
    )
    vexxo_tax = _money(vexxo_fee * _rate(capabilities.get("payout_fee_vat_rate", "0.19")))

    total_fee = _money(provider_fee + provider_tax + vexxo_fee + vexxo_tax)
    total_charge = _money(amount_value + total_fee)

    return {
        "country": str(country or "CO").upper(),
        "provider": str(provider or "").strip(),
        "rail": str(rail or "").strip(),
        "plan": capabilities.get("plan"),
        "amount": str(amount_value),
        "provider_cost": str(provider_fee),
        "provider_tax": str(provider_tax),
        "vexxo_fee": str(vexxo_fee),
        "vexxo_tax": str(vexxo_tax),
        "tax_cost": str(_money(provider_tax + vexxo_tax)),
        "total_fee": str(total_fee),
        "total_charge": str(total_charge),
        "breakdown": {
            "provider": {
                "percentage": str(provider_profile["percentage"]),
                "flat": str(provider_profile["flat"]),
                "vat_rate": str(provider_profile["vat_rate"]),
                "fee": str(provider_fee),
                "tax": str(provider_tax),
            },
            "vexxo": {
                "percentage": str(_rate(capabilities.get("payout_fee_percentage", "0"))),
                "flat": str(_money(capabilities.get("payout_fee_flat", "0"))),
                "vat_rate": str(_rate(capabilities.get("payout_fee_vat_rate", "0.19"))),
                "fee": str(vexxo_fee),
                "tax": str(vexxo_tax),
            },
        },
    }
