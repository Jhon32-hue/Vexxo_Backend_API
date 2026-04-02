"""
Servicios compartidos de planes, uso y enforcement comercial.

Descripcion general:
- centraliza capabilities efectivas, tracking de uso y respuestas estandar de
  limites para mobile-first
- evita que cada modulo reinvente mensajes, payloads o eventos de upgrade

Analisis detallado:
- el enforcement final sigue viviendo en guards de cada bounded context
- este modulo provee piezas comunes para que `accounts`, `alerts`, `payments`
  y futuras apps apliquen la misma semantica de producto
- la intencion es dejar listo el camino para GCP, outbox y growth events sin
  acoplar el dominio a un proveedor concreto
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from common.domain_events import EventNames, EventPriority
from identity.users.domain import build_identity_entity_payload
from identity.users.domain.plan_matrix import get_plan_capabilities, resolve_plan_code
from identity.users.services.event_service import publish_user_event_after_commit
from identity.users.services.product_usage_projection_service import get_user_usage_projection_snapshot
from payments.payment_intents.platform_limits import (
    resolve_payment_platform_limits,
    resolve_payout_platform_limits,
)

ZERO = Decimal("0.00")


def effective_plan_for_user(user) -> str:
    return resolve_plan_code(getattr(user, "plan", None))


def capabilities_for_user(user) -> dict[str, Any]:
    if user is None:
        return get_plan_capabilities("free")
    if hasattr(user, "get_plan_config"):
        config = dict(user.get_plan_config() or {})
    else:
        config = get_plan_capabilities(getattr(user, "plan", "free"))
    config["plan"] = resolve_plan_code(config.get("plan") or getattr(user, "plan", "free"))
    return config


def get_user_usage_snapshot(user, *, reference=None) -> dict[str, Any]:
    return get_user_usage_projection_snapshot(user, allow_rebuild=reference is None)


def build_plan_limit_error(
    *,
    user,
    metric: str,
    current,
    limit,
    detail: str,
    source: str,
    upgrade_plan: str = "pro",
    permission_code: str = "",
    extra: dict | None = None,
) -> dict[str, Any]:
    return {
        "code": "plan_limit_exceeded",
        "domain": "plan_limits",
        "metric": metric,
        "plan": effective_plan_for_user(user),
        "limit": limit,
        "current": current,
        "upgrade_plan": upgrade_plan,
        "upgrade_hint": detail,
        "permission_code": permission_code,
        "source": source,
        "detail": detail,
        **(extra or {}),
    }


def publish_upgrade_triggered_event(
    *,
    user,
    metric: str,
    current,
    limit,
    source: str,
    detail: str,
    upgrade_plan: str = "pro",
    permission_code: str = "",
    extra: dict | None = None,
) -> None:
    payload = build_identity_entity_payload(
        user=user,
        entity_type="upgrade_trigger",
        entity_id=f"{metric}:{timezone.now().strftime('%Y%m')}",
        extra={
            "metric": metric,
            "current": current,
            "limit": limit,
            "detail": detail,
            "source": source,
            "upgrade_plan": upgrade_plan,
            "permission_code": permission_code,
            **(extra or {}),
        },
    )
    publish_user_event_after_commit(
        event_type=EventNames.GROWTH_UPGRADE_TRIGGERED,
        payload=payload,
        metadata={
            "source": source,
            "context": "system",
        },
        priority=EventPriority.LOW,
    )


def raise_plan_limit_error(
    *,
    user,
    metric: str,
    current,
    limit,
    detail: str,
    source: str,
    upgrade_plan: str = "pro",
    permission_code: str = "",
    extra: dict | None = None,
):
    publish_upgrade_triggered_event(
        user=user,
        metric=metric,
        current=current,
        limit=limit,
        detail=detail,
        source=source,
        upgrade_plan=upgrade_plan,
        permission_code=permission_code,
        extra=extra,
    )
    raise serializers.ValidationError(
        {
            "detail": detail,
            "error": build_plan_limit_error(
                user=user,
                metric=metric,
                current=current,
                limit=limit,
                detail=detail,
                source=source,
                upgrade_plan=upgrade_plan,
                permission_code=permission_code,
                extra=extra,
            ),
        }
    )


def raise_operational_limit_error(
    *,
    metric: str,
    current,
    limit,
    detail: str,
    source: str,
    extra: dict | None = None,
):
    raise serializers.ValidationError(
        {
            "detail": detail,
            "error": {
                "code": "operational_limit_exceeded",
                "domain": "operational_limits",
                "metric": metric,
                "limit": limit,
                "current": current,
                "source": source,
                "detail": detail,
                **(extra or {}),
            },
        }
    )


def validate_rules_limit(user, *, source: str = "alerts.rules") -> None:
    capabilities = capabilities_for_user(user)
    limit = capabilities.get("max_rules")
    if limit is None:
        return
    current = get_user_usage_snapshot(user)["rules_count"]
    if current >= limit:
        raise_plan_limit_error(
            user=user,
            metric="max_rules",
            current=current,
            limit=limit,
            detail="Puedes crear mas reglas automaticas con Pro.",
            source=source,
            permission_code="automation.rules.extended.enabled",
        )


def validate_scheduled_payments_limit(user, *, source: str = "transactions.scheduled_payments") -> None:
    capabilities = capabilities_for_user(user)
    limit = capabilities.get("max_scheduled_payments")
    if limit is None:
        return
    current = get_user_usage_snapshot(user)["scheduled_payments_active_count"]
    if current >= limit:
        raise_plan_limit_error(
            user=user,
            metric="max_scheduled_payments",
            current=current,
            limit=limit,
            detail="Con Pro puedes crear mas pagos programados activos.",
            source=source,
            permission_code="payments.embedded.enabled",
        )


def validate_embedded_payment_allowed(
    user,
    *,
    amount,
    provider: str = "",
    rail: str = "",
    source: str = "transactions.embedded_payment",
) -> None:
    capabilities = capabilities_for_user(user)
    if not capabilities.get("embedded_payments_enabled", False):
        raise_plan_limit_error(
            user=user,
            metric="embedded_payments_enabled",
            current=0,
            limit=1,
            detail="Tu plan no tiene pagos embebidos habilitados.",
            source=source,
            permission_code="payments.embedded.enabled",
        )

    usage = get_user_usage_snapshot(user)
    amount_value = Decimal(str(amount or ZERO))
    max_single_amount = capabilities.get("max_single_payment_amount")
    if max_single_amount is not None and amount_value > Decimal(str(max_single_amount)):
        raise_plan_limit_error(
            user=user,
            metric="max_single_payment_amount",
            current=str(amount_value),
            limit=str(max_single_amount),
            detail="Ese monto excede el limite por pago de tu plan actual.",
            source=source,
            permission_code="payments.embedded.enabled",
        )

    max_daily_volume = capabilities.get("max_daily_payment_volume")
    if max_daily_volume is not None:
        current_volume_day = Decimal(str(usage["payments_volume_day"]))
        projected_day = current_volume_day + amount_value
        if projected_day > Decimal(str(max_daily_volume)):
            raise_plan_limit_error(
                user=user,
                metric="max_daily_payment_volume",
                current=str(projected_day),
                limit=str(max_daily_volume),
                detail="Con Pro puedes mover un mayor volumen diario de pagos dentro de la app.",
                source=source,
                permission_code="payments.embedded.enabled",
            )

    max_payments = capabilities.get("max_payments_per_month")
    if max_payments is not None and usage["payments_count_month"] >= max_payments:
        raise_plan_limit_error(
            user=user,
            metric="max_payments_per_month",
            current=usage["payments_count_month"],
            limit=max_payments,
            detail="Con Pro puedes ejecutar mas pagos dentro de la app.",
            source=source,
            permission_code="payments.embedded.enabled",
        )

    max_volume = capabilities.get("max_monthly_payment_volume")
    if max_volume is not None:
        current_volume = Decimal(str(usage["payments_volume_month"]))
        projected = current_volume + amount_value
        if projected > Decimal(str(max_volume)):
            raise_plan_limit_error(
                user=user,
                metric="max_monthly_payment_volume",
                current=str(projected),
                limit=str(max_volume),
                detail="Alcanza Pro para mover un mayor volumen de pagos desde la app.",
                source=source,
                permission_code="payments.embedded.enabled",
            )

    platform_limits = resolve_payment_platform_limits(provider=provider, rail=rail)
    if platform_limits["single_cap"] and amount_value > platform_limits["single_cap"]:
        raise_operational_limit_error(
            metric="platform_single_payment_cap",
            current=str(amount_value),
            limit=str(platform_limits["single_cap"]),
            detail="Ese pago supera el monto operativo permitido por Vexxo para este proveedor o rail.",
            source=source,
            extra={
                "provider": platform_limits["provider"],
                "rail": platform_limits["rail"],
            },
        )
    if platform_limits["daily_cap"]:
        projected_platform_day = Decimal(str(usage["payments_volume_day"])) + amount_value
        if projected_platform_day > platform_limits["daily_cap"]:
            raise_operational_limit_error(
                metric="platform_daily_payment_cap",
                current=str(projected_platform_day),
                limit=str(platform_limits["daily_cap"]),
                detail="Vexxo alcanzo el cap operativo diario permitido para ese proveedor o rail.",
                source=source,
                extra={
                    "provider": platform_limits["provider"],
                    "rail": platform_limits["rail"],
                },
            )


def validate_payout_allowed(
    user,
    *,
    amount,
    provider: str = "",
    rail: str = "",
    source: str = "payments.payouts",
) -> None:
    capabilities = capabilities_for_user(user)
    if not capabilities.get("payouts_enabled", False):
        raise_plan_limit_error(
            user=user,
            metric="payouts_enabled",
            current=0,
            limit=1,
            detail="Tu plan no tiene dispersiones o transferencias salientes avanzadas habilitadas.",
            source=source,
            permission_code="payments.payouts.enabled",
        )

    usage = get_user_usage_snapshot(user)
    max_payouts = capabilities.get("max_payouts_per_month")
    if max_payouts is not None and usage["payouts_count_month"] >= max_payouts:
        raise_plan_limit_error(
            user=user,
            metric="max_payouts_per_month",
            current=usage["payouts_count_month"],
            limit=max_payouts,
            detail="Con Pro puedes ejecutar mas dispersiones o transferencias salientes.",
            source=source,
            permission_code="payments.payouts.enabled",
        )

    amount_value = Decimal(str(amount or ZERO))
    max_daily_volume = capabilities.get("max_daily_payout_volume")
    if max_daily_volume is not None:
        current_volume_day = Decimal(str(usage["payouts_volume_day"]))
        projected_day = current_volume_day + amount_value
        if projected_day > Decimal(str(max_daily_volume)):
            raise_plan_limit_error(
                user=user,
                metric="max_daily_payout_volume",
                current=str(projected_day),
                limit=str(max_daily_volume),
                detail="Con Pro puedes mover un mayor volumen diario de dispersiones.",
                source=source,
                permission_code="payments.payouts.enabled",
            )

    max_payout_amount = capabilities.get("max_payout_amount")
    if max_payout_amount is not None and amount_value > Decimal(str(max_payout_amount)):
        raise_plan_limit_error(
            user=user,
            metric="max_payout_amount",
            current=str(amount_value),
            limit=str(max_payout_amount),
            detail="Ese monto excede el limite por transferencia de tu plan actual.",
            source=source,
            permission_code="payments.payouts.enabled",
        )

    max_volume = capabilities.get("max_monthly_payout_volume")
    if max_volume is not None:
        current_volume = Decimal(str(usage["payouts_volume_month"]))
        projected = current_volume + amount_value
        if projected > Decimal(str(max_volume)):
            raise_plan_limit_error(
                user=user,
                metric="max_monthly_payout_volume",
                current=str(projected),
                limit=str(max_volume),
                detail="Con Pro puedes mover un mayor volumen mensual de dispersiones.",
                source=source,
                permission_code="payments.payouts.enabled",
            )

    platform_limits = resolve_payout_platform_limits(provider=provider, rail=rail)
    if platform_limits["single_cap"] and amount_value > platform_limits["single_cap"]:
        raise_operational_limit_error(
            metric="platform_single_payout_cap",
            current=str(amount_value),
            limit=str(platform_limits["single_cap"]),
            detail="Esa dispersion supera el monto operativo permitido por Vexxo para este proveedor o rail.",
            source=source,
            extra={
                "provider": platform_limits["provider"],
                "rail": platform_limits["rail"],
            },
        )
    if platform_limits["daily_cap"]:
        projected_platform_day = Decimal(str(usage["payouts_volume_day"])) + amount_value
        if projected_platform_day > platform_limits["daily_cap"]:
            raise_operational_limit_error(
                metric="platform_daily_payout_cap",
                current=str(projected_platform_day),
                limit=str(platform_limits["daily_cap"]),
                detail="Vexxo alcanzo el cap operativo diario permitido para dispersiones en ese proveedor o rail.",
                source=source,
                extra={
                    "provider": platform_limits["provider"],
                    "rail": platform_limits["rail"],
                },
            )


def allow_ai_request(user, *, source: str = "alerts.ai", feature: str = "alert_enrichment") -> bool:
    capabilities = capabilities_for_user(user)
    limit = capabilities.get("ai_requests_per_month")
    if limit is None:
        return True

    current = get_user_usage_snapshot(user)["ai_used_month"]
    if current < limit:
        return True

    publish_upgrade_triggered_event(
        user=user,
        metric="ai_requests_per_month",
        current=current,
        limit=limit,
        detail="Con Pro puedes seguir recibiendo insights y explicaciones inteligentes.",
        source=source,
        permission_code="ai.advanced_insights.enabled",
        extra={"feature": feature},
    )
    return False
