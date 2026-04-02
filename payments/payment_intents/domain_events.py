"""
Contratos y payload builders del bounded context de pagos.

Hoy el transporte todavia es liviano y sin outbox propio, pero el contrato del
dominio queda definido desde ya para mobile, workers e integraciones.
"""

from __future__ import annotations

from common.domain_events import EventNames


class PaymentDomainEventTypes:
    PAYMENT_ORDER_REQUESTED = EventNames.PAYMENT_ORDER_REQUESTED
    PAYMENT_INTENT_CREATED = EventNames.PAYMENT_INTENT_CREATED
    PAYMENT_INTENT_DISPATCHED = EventNames.PAYMENT_INTENT_DISPATCHED
    PAYMENT_INTENT_REQUIRES_ACTION = EventNames.PAYMENT_INTENT_REQUIRES_ACTION
    PAYMENT_INTENT_PROCESSING = EventNames.PAYMENT_INTENT_PROCESSING
    PAYMENT_INTENT_SUCCEEDED = EventNames.PAYMENT_INTENT_SUCCEEDED
    PAYMENT_INTENT_FAILED = EventNames.PAYMENT_INTENT_FAILED
    PAYMENT_INTENT_CANCELLED = EventNames.PAYMENT_INTENT_CANCELLED
    PAYMENT_INTENT_SETTLED = EventNames.PAYMENT_INTENT_SETTLED
    PAYMENT_FEE_CALCULATED = EventNames.PAYMENT_FEE_CALCULATED
    PAYMENT_PROVIDER_REFERENCE_RECORDED = EventNames.PAYMENT_PROVIDER_REFERENCE_RECORDED
    PAYMENT_RECURRING_TEMPLATE_CREATED = EventNames.PAYMENT_RECURRING_TEMPLATE_CREATED
    PAYMENT_RECURRING_TEMPLATE_UPDATED = EventNames.PAYMENT_RECURRING_TEMPLATE_UPDATED
    PAYMENT_RECURRING_RUN_REQUESTED = EventNames.PAYMENT_RECURRING_RUN_REQUESTED
    PAYMENT_PAYOUT_REQUESTED = EventNames.PAYMENT_PAYOUT_REQUESTED
    PAYMENT_PAYOUT_SUCCEEDED = EventNames.PAYMENT_PAYOUT_SUCCEEDED
    PAYMENT_PAYOUT_FAILED = EventNames.PAYMENT_PAYOUT_FAILED


def build_payment_intent_payload(payment_intent, *, change: str, extra: dict | None = None) -> dict:
    payload = {
        "payment_intent_id": str(payment_intent.pk),
        "owner_id": str(payment_intent.owner_id),
        "payment_type": payment_intent.payment_type,
        "rail": payment_intent.rail,
        "status": payment_intent.status,
        "provider": payment_intent.provider,
        "amount": str(payment_intent.amount),
        "currency": payment_intent.currency,
        "internal_reference": payment_intent.internal_reference,
        "external_reference": payment_intent.external_reference,
        "invoice_reference": payment_intent.invoice_reference,
        "provider_intent_id": payment_intent.provider_intent_id,
        "provider_reference": payment_intent.provider_reference,
        "provider_cus": payment_intent.provider_cus,
        "beneficiary_name": payment_intent.beneficiary_name,
        "beneficiary_document": payment_intent.beneficiary_document,
        "beneficiary_account_ref": payment_intent.beneficiary_account_ref,
        "pricing_snapshot": payment_intent.pricing_snapshot or {},
        "fee_breakdown": payment_intent.fee_breakdown or {},
        "tax_breakdown": payment_intent.tax_breakdown or {},
        "change": change,
    }
    if extra:
        payload.update(extra)
    return payload


def build_payment_usage_transition(*, before_counted: bool, after_counted: bool, amount) -> dict:
    return {
        "before_counted": bool(before_counted),
        "after_counted": bool(after_counted),
        "amount": str(amount),
    }


def build_payment_fee_payload(*, payment_intent, pricing_snapshot: dict) -> dict:
    return {
        "payment_intent_id": str(payment_intent.pk),
        "owner_id": str(payment_intent.owner_id),
        "provider": payment_intent.provider,
        "rail": payment_intent.rail,
        "payment_type": payment_intent.payment_type,
        "amount": str(payment_intent.amount),
        "currency": payment_intent.currency,
        "pricing_snapshot": pricing_snapshot or {},
    }
