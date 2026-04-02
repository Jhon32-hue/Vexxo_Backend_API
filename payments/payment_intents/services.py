"""
Servicios de orquestacion de payment intents.

Estado actual:
- este modulo define el punto canonico donde debe vivir el gating comercial de
  pagos embebidos
- coordina intents persistentes, pricing, outbox y transiciones de estado para
  que futuras APIs o workers reutilicen el mismo flujo

Relaciones:
- usa `identity.users.services.product_access_service` para aplicar limites y
  upgrade hints
- debera coordinarse con `integrations_service` o PSP/retailer adapters para
  crear intents externos y recibir callbacks
- la materializacion contable final deberia terminar en `finance.transactions`
  cuando el proveedor confirme el pago
"""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from common.domain_events import EventPriority
from identity.users.services.product_access_service import validate_embedded_payment_allowed
from payments.payment_intents.domain_events import (
    PaymentDomainEventTypes,
    build_payment_fee_payload,
    build_payment_intent_payload,
    build_payment_usage_transition,
)
from payments.payment_intents.event_service import publish_payment_event_after_commit
from payments.payment_intents.models import PaymentIntent
from payments.payment_intents.pricing_service import calculate_embedded_payment_pricing


def _stable_payment_intent_key(*, user, amount, currency: str, provider: str, external_reference: str, source: str) -> str:
    raw = json.dumps(
        {
            "owner_id": str(user.pk),
            "amount": str(Decimal(str(amount or 0))),
            "currency": str(currency or "").strip().upper(),
            "provider": str(provider or "").strip().lower(),
            "external_reference": str(external_reference or "").strip(),
            "source": str(source or "").strip(),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _assert_owned_by_user(user, obj, field_name: str):
    if obj is not None and getattr(obj, "owner_id", None) and obj.owner_id != user.id:
        raise serializers.ValidationError({field_name: "No pertenece al usuario autenticado."})


def _counts_for_usage(status: str) -> bool:
    return str(status or "").strip() in {
        PaymentIntent.Status.CREATED,
        PaymentIntent.Status.DISPATCHED,
        PaymentIntent.Status.PROCESSING,
        PaymentIntent.Status.REQUIRES_ACTION,
        PaymentIntent.Status.SUCCEEDED,
        PaymentIntent.Status.SETTLED,
        PaymentIntent.Status.DISPUTED,
    }


def _publish_payment_intent_event(
    *,
    payment_intent: PaymentIntent,
    event_type: str,
    change: str,
    metadata: dict | None = None,
    extra: dict | None = None,
):
    publish_payment_event_after_commit(
        event_type=event_type,
        payload=build_payment_intent_payload(payment_intent, change=change, extra=extra),
        metadata={
            "source": "payments.payment_intents.services",
            "aggregate_type": "payment",
            "aggregate_id": str(payment_intent.pk),
            "projection_event_key": f"payment-intent:{payment_intent.pk}:{event_type}:{change}",
            **(metadata or {}),
        },
        priority=EventPriority.NORMAL,
        correlation_id=str((metadata or {}).get("correlation_id") or "") or None,
        causation_id=str((metadata or {}).get("causation_id") or "") or None,
    )


def _publish_payment_usage_transition(
    *,
    payment_intent: PaymentIntent,
    event_type: str,
    change: str,
    before_status: str,
    after_status: str,
    metadata: dict | None = None,
):
    _publish_payment_intent_event(
        payment_intent=payment_intent,
        event_type=event_type,
        change=change,
        metadata=metadata,
        extra={
            "usage_transition": build_payment_usage_transition(
                before_counted=_counts_for_usage(before_status),
                after_counted=_counts_for_usage(after_status),
                amount=payment_intent.amount,
            ),
            "before_status": before_status,
            "after_status": after_status,
        },
    )


def validate_payment_intent_allowed(*, user, amount, source: str = "payments.payment_intents.create") -> None:
    validate_embedded_payment_allowed(
        user,
        amount=amount,
        provider="",
        rail="",
        source=source,
    )


def validate_payment_intent_allowed_for_route(
    *,
    user,
    amount,
    provider: str,
    rail: str,
    source: str = "payments.payment_intents.create",
) -> None:
    """
    Guard canonico para intents de pago embebido.

    Debe llamarse antes de crear un comando hacia un integrador externo o PSP.
    """
    validate_embedded_payment_allowed(
        user,
        amount=amount,
        provider=provider,
        rail=rail,
        source=source,
    )


def build_payment_intent_command(
    *,
    user,
    amount,
    currency: str,
    provider: str,
    external_reference: str = "",
    payment_type: str = PaymentIntent.PaymentType.OTHER,
    rail: str = PaymentIntent.Rail.OTHER,
    account=None,
    category=None,
    vendor=None,
    beneficiary_name: str = "",
    beneficiary_document: str = "",
    beneficiary_account_ref: str = "",
    invoice_reference: str = "",
    source: str = "payments.payment_intents.create",
) -> dict:
    """
    Construye un comando estable para un integrador externo.

    Este helper no persiste nada todavia; sirve como esqueleto comun mientras
    adapters o integradores externos se conectan al bounded context.
    """
    validate_payment_intent_allowed_for_route(
        user=user,
        amount=amount,
        provider=provider,
        rail=rail,
        source=source,
    )
    return {
        "owner_id": str(user.pk),
        "amount": str(amount),
        "currency": str(currency or "").strip(),
        "provider": str(provider or "").strip(),
        "payment_type": str(payment_type or "").strip(),
        "rail": str(rail or "").strip(),
        "account_id": str(getattr(account, "pk", "") or ""),
        "category_id": str(getattr(category, "pk", "") or ""),
        "vendor_id": str(getattr(vendor, "pk", "") or ""),
        "beneficiary_name": str(beneficiary_name or "").strip(),
        "beneficiary_document": str(beneficiary_document or "").strip(),
        "beneficiary_account_ref": str(beneficiary_account_ref or "").strip(),
        "external_reference": str(external_reference or "").strip(),
        "invoice_reference": str(invoice_reference or "").strip(),
        "source": source,
    }


@transaction.atomic
def create_payment_intent(
    *,
    user,
    amount,
    currency: str,
    provider: str,
    external_reference: str = "",
    payment_type: str = PaymentIntent.PaymentType.OTHER,
    rail: str = PaymentIntent.Rail.OTHER,
    account=None,
    category=None,
    vendor=None,
    beneficiary_name: str = "",
    beneficiary_document: str = "",
    beneficiary_account_ref: str = "",
    invoice_reference: str = "",
    source: str = "payments.payment_intents.create",
    idempotency_key: str = "",
    provider_pricing: dict | None = None,
):
    """
    Crea o reutiliza el intent canónico previo al envío al PSP.

    Este es el punto correcto para:
    - aplicar guards comerciales
    - guardar idempotencia del request
    - dejar un registro persistente antes de hablar con integradores externos
    """
    normalized_key = str(idempotency_key or "").strip()
    _assert_owned_by_user(user, account, "account")
    _assert_owned_by_user(user, category, "category")
    _assert_owned_by_user(user, vendor, "vendor")
    if not normalized_key and str(external_reference or "").strip():
        normalized_key = _stable_payment_intent_key(
            user=user,
            amount=amount,
            currency=currency,
            provider=provider,
            external_reference=external_reference,
            source=source,
        )
    if not normalized_key:
        normalized_key = uuid.uuid4().hex
    command = build_payment_intent_command(
        user=user,
        amount=amount,
        currency=currency,
        provider=provider,
        external_reference=external_reference,
        payment_type=payment_type,
        rail=rail,
        account=account,
        category=category,
        vendor=vendor,
        beneficiary_name=beneficiary_name,
        beneficiary_document=beneficiary_document,
        beneficiary_account_ref=beneficiary_account_ref,
        invoice_reference=invoice_reference,
        source=source,
    )
    pricing_snapshot = calculate_embedded_payment_pricing(
        user=user,
        amount=amount,
        provider=provider,
        rail=rail,
        payment_type=payment_type,
        provider_pricing=provider_pricing,
    )
    payment_intent, _created = PaymentIntent.objects.get_or_create(
        idempotency_key=normalized_key,
        defaults={
            "owner": user,
            "account": account,
            "category": category,
            "vendor": vendor,
            "payment_type": payment_type,
            "rail": rail,
            "amount": Decimal(str(amount)),
            "currency": str(currency or "").strip().upper() or "COP",
            "provider": str(provider or "").strip(),
            "internal_reference": uuid.uuid4().hex[:24],
            "external_reference": str(external_reference or "").strip() or uuid.uuid4().hex[:32],
            "invoice_reference": str(invoice_reference or "").strip(),
            "beneficiary_name": str(beneficiary_name or "").strip(),
            "beneficiary_document": str(beneficiary_document or "").strip(),
            "beneficiary_account_ref": str(beneficiary_account_ref or "").strip(),
            "source": source,
            "command_payload": command,
            "destination_payload": {
                "beneficiary_name": str(beneficiary_name or "").strip(),
                "beneficiary_document": str(beneficiary_document or "").strip(),
                "beneficiary_account_ref": str(beneficiary_account_ref or "").strip(),
            },
            "pricing_snapshot": pricing_snapshot,
            "fee_breakdown": pricing_snapshot.get("breakdown", {}).get("vexxo", {}),
            "tax_breakdown": {
                "provider_tax": pricing_snapshot.get("provider_tax", "0.00"),
                "vexxo_tax": pricing_snapshot.get("vexxo_tax", "0.00"),
                "tax_cost": pricing_snapshot.get("tax_cost", "0.00"),
            },
        },
    )
    if _created:
        publish_payment_event_after_commit(
            event_type=PaymentDomainEventTypes.PAYMENT_ORDER_REQUESTED,
            payload=build_payment_intent_payload(payment_intent, change="payment_order_requested"),
            metadata={"source": source, "projection_event_key": f"payment-intent:{payment_intent.pk}:order-requested"},
            priority=EventPriority.NORMAL,
        )
        publish_payment_event_after_commit(
            event_type=PaymentDomainEventTypes.PAYMENT_FEE_CALCULATED,
            payload=build_payment_fee_payload(payment_intent=payment_intent, pricing_snapshot=pricing_snapshot),
            metadata={
                "source": source,
                "aggregate_type": "payment",
                "aggregate_id": str(payment_intent.pk),
                "projection_event_key": f"payment-fee:{payment_intent.pk}",
            },
            priority=EventPriority.LOW,
        )
        _publish_payment_usage_transition(
            payment_intent=payment_intent,
            event_type=PaymentDomainEventTypes.PAYMENT_INTENT_CREATED,
            change="payment_intent_created",
            before_status="",
            after_status=payment_intent.status,
            metadata={"source": source},
        )
    return payment_intent


def mark_payment_intent_dispatched(
    payment_intent: PaymentIntent,
    *,
    provider_intent_id: str = "",
    provider_metadata: dict | None = None,
):
    before_status = payment_intent.status
    updated = payment_intent.mark_dispatched(
        provider_intent_id=provider_intent_id,
        provider_metadata=provider_metadata,
        commit=True,
    )
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_DISPATCHED,
        change="payment_intent_dispatched",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_dispatched"},
    )
    return updated


def mark_payment_intent_processing(payment_intent: PaymentIntent, *, provider_metadata: dict | None = None):
    before_status = payment_intent.status
    updated = payment_intent.mark_processing(provider_metadata=provider_metadata, commit=True)
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_PROCESSING,
        change="payment_intent_processing",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_processing"},
    )
    return updated


def mark_payment_intent_requires_action(payment_intent: PaymentIntent, *, provider_metadata: dict | None = None):
    before_status = payment_intent.status
    updated = payment_intent.mark_requires_action(provider_metadata=provider_metadata, commit=True)
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_REQUIRES_ACTION,
        change="payment_intent_requires_action",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_requires_action"},
    )
    return updated


def mark_payment_intent_succeeded(
    payment_intent: PaymentIntent,
    *,
    provider_intent_id: str = "",
    provider_metadata: dict | None = None,
    materialize_ledger: bool = True,
):
    before_status = payment_intent.status
    updated = payment_intent.mark_succeeded(
        provider_intent_id=provider_intent_id,
        provider_metadata=provider_metadata,
        commit=True,
    )
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_SUCCEEDED,
        change="payment_intent_succeeded",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_succeeded"},
    )
    if materialize_ledger:
        from finance.transactions.payment_materialization_service import materialize_transaction_from_payment_intent

        materialize_transaction_from_payment_intent(updated)
    return updated


def mark_payment_intent_settled(payment_intent: PaymentIntent, *, provider_metadata: dict | None = None):
    before_status = payment_intent.status
    updated = payment_intent.mark_settled(provider_metadata=provider_metadata, commit=True)
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_SETTLED,
        change="payment_intent_settled",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_settled"},
    )
    from finance.transactions.payment_materialization_service import materialize_transaction_from_payment_intent

    materialize_transaction_from_payment_intent(updated)
    return updated


def mark_payment_intent_failed(
    payment_intent: PaymentIntent,
    *,
    failure_code: str = "",
    failure_message: str = "",
    provider_metadata: dict | None = None,
):
    before_status = payment_intent.status
    updated = payment_intent.mark_failed(
        failure_code=failure_code,
        failure_message=failure_message,
        provider_metadata=provider_metadata,
        commit=True,
    )
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_FAILED,
        change="payment_intent_failed",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_failed"},
    )
    return updated


def mark_payment_intent_cancelled(
    payment_intent: PaymentIntent,
    *,
    failure_message: str = "",
    provider_metadata: dict | None = None,
):
    before_status = payment_intent.status
    updated = payment_intent.mark_cancelled(
        failure_message=failure_message,
        provider_metadata=provider_metadata,
        commit=True,
    )
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_CANCELLED,
        change="payment_intent_cancelled",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_cancelled"},
    )
    return updated


def mark_payment_intent_reversed(
    payment_intent: PaymentIntent,
    *,
    failure_message: str = "",
    provider_metadata: dict | None = None,
):
    before_status = payment_intent.status
    updated = payment_intent.mark_reversed(
        failure_message=failure_message,
        provider_metadata=provider_metadata,
        commit=True,
    )
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_REVERSED,
        change="payment_intent_reversed",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_reversed"},
    )
    return updated


def mark_payment_intent_disputed(
    payment_intent: PaymentIntent,
    *,
    failure_message: str = "",
    provider_metadata: dict | None = None,
):
    before_status = payment_intent.status
    updated = payment_intent.mark_disputed(
        failure_message=failure_message,
        provider_metadata=provider_metadata,
        commit=True,
    )
    _publish_payment_usage_transition(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_INTENT_DISPUTED,
        change="payment_intent_disputed",
        before_status=before_status,
        after_status=updated.status,
        metadata={"source": "payments.payment_intents.mark_disputed"},
    )
    return updated


def record_payment_provider_reference(
    payment_intent: PaymentIntent,
    *,
    provider_reference: str = "",
    provider_cus: str = "",
    provider_metadata: dict | None = None,
):
    updated = payment_intent.record_provider_reference(
        provider_reference=provider_reference,
        provider_cus=provider_cus,
        provider_metadata=provider_metadata,
        commit=True,
    )
    _publish_payment_intent_event(
        payment_intent=updated,
        event_type=PaymentDomainEventTypes.PAYMENT_PROVIDER_REFERENCE_RECORDED,
        change="provider_reference_recorded",
        metadata={"source": "payments.payment_intents.record_provider_reference"},
    )
    return updated
