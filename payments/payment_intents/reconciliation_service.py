"""
Servicios base de conciliacion y artefactos operativos de pagos.

No depende de un PSP concreto. Registra settlement y casos operativos
reconciliables cuando el callback o un worker aportan informacion nueva.
"""

from __future__ import annotations

from decimal import Decimal

from payments.payment_intents.models import PaymentIntent, PaymentOperationalCase, PaymentSettlementRecord


def record_payment_settlement(
    *,
    payment_intent: PaymentIntent | None,
    provider: str,
    rail: str = "",
    settlement_reference: str = "",
    provider_reference: str = "",
    provider_cus: str = "",
    amount=0,
    settlement_payload: dict | None = None,
) -> PaymentSettlementRecord:
    amount_value = Decimal(str(amount or "0"))
    provider_value = str(provider or "").strip()
    settlement_key = str(settlement_reference or provider_reference or provider_cus or "").strip()[:128]
    if not settlement_key and payment_intent is not None:
        settlement_key = f"intent:{payment_intent.pk}"[:128]
    settlement, _created = PaymentSettlementRecord.objects.get_or_create(
        provider=provider_value,
        settlement_reference=settlement_key,
        defaults={
            "payment_intent": payment_intent,
            "rail": str(rail or "").strip(),
            "provider_reference": str(provider_reference or "").strip()[:128],
            "provider_cus": str(provider_cus or "").strip()[:64],
            "amount": amount_value,
            "fee_snapshot": dict(getattr(payment_intent, "pricing_snapshot", {}) or {}),
            "settlement_payload": settlement_payload or {},
            "status": PaymentSettlementRecord.Status.RECORDED,
        },
    )
    if not _created:
        settlement.payment_intent = payment_intent or settlement.payment_intent
        settlement.provider = str(provider or settlement.provider).strip()
        settlement.rail = str(rail or settlement.rail).strip()
        settlement.provider_reference = str(provider_reference or settlement.provider_reference).strip()[:128]
        settlement.provider_cus = str(provider_cus or settlement.provider_cus).strip()[:64]
        settlement.amount = amount_value or settlement.amount
        settlement.fee_snapshot = dict(getattr(payment_intent, "pricing_snapshot", {}) or settlement.fee_snapshot or {})
        settlement.settlement_payload = settlement_payload or settlement.settlement_payload or {}
        settlement.save(
            update_fields=[
                "payment_intent",
                "provider",
                "rail",
                "provider_reference",
                "provider_cus",
                "amount",
                "fee_snapshot",
                "settlement_payload",
            ]
        )
    return settlement


def open_payment_operational_case(
    *,
    payment_intent: PaymentIntent | None,
    provider: str,
    kind: str,
    amount=0,
    currency: str = "COP",
    provider_reference: str = "",
    provider_case_reference: str = "",
    details: dict | None = None,
) -> PaymentOperationalCase:
    provider_value = str(provider or "").strip()
    kind_value = str(kind or PaymentOperationalCase.Kind.ERROR).strip()
    case_reference = str(provider_case_reference or "").strip()[:128]
    if not case_reference:
        case_reference = f"{kind_value}:{provider_reference or getattr(payment_intent, 'pk', '')}"[:128]
    case, _created = PaymentOperationalCase.objects.get_or_create(
        provider=provider_value,
        provider_case_reference=case_reference,
        defaults={
            "payment_intent": payment_intent,
            "kind": kind_value,
            "provider_reference": str(provider_reference or "").strip()[:128],
            "amount": Decimal(str(amount or "0")),
            "currency": str(currency or "COP").strip().upper() or "COP",
            "details": details or {},
        },
    )
    return case
