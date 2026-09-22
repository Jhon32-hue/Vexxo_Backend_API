"""
Procesamiento canonico de callbacks de PSP, retailers o workers internos.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from security.validators import sanitize_external_payload

from common.domain_events import EventPriority
from payments.payment_intents.adapters import PaymentProviderContractError, get_payment_provider_adapter
from payments.payment_intents.domain_events import PaymentDomainEventTypes
from payments.payment_intents.event_service import publish_payment_event_after_commit
from payments.payment_intents.models import PaymentIntent, PaymentOperationalCase, PaymentProviderCallbackReceipt
from payments.payment_intents.reconciliation_service import (
    open_payment_operational_case,
    record_payment_settlement,
)
from payments.payment_intents.services import (
    mark_payment_intent_cancelled,
    mark_payment_intent_dispatched,
    mark_payment_intent_disputed,
    mark_payment_intent_failed,
    mark_payment_intent_processing,
    mark_payment_intent_reversed,
    mark_payment_intent_requires_action,
    mark_payment_intent_settled,
    mark_payment_intent_succeeded,
    record_payment_provider_reference,
)
from payments.payment_intents.state_machine import can_apply_provider_transition


def _raw_callback_receipt_key(provider: str, payload: dict, headers: dict | None = None) -> str:
    raw = json.dumps(
        {
            "provider": str(provider or "").strip().lower(),
            "payload": payload or {},
            "headers": headers or {},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:160]


def _callback_receipt_key(provider: str, normalized: dict) -> str:
    identity = {
        "provider": str(provider or "").strip().lower(),
        "provider_event_type": str(normalized.get("provider_event_type") or "").strip(),
        "payment_intent_id": str(normalized.get("payment_intent_id") or "").strip(),
        "provider_intent_id": str(normalized.get("provider_intent_id") or "").strip(),
        "external_reference": str(normalized.get("external_reference") or "").strip(),
        "provider_reference": str(normalized.get("provider_reference") or "").strip(),
        "status": str(normalized.get("status") or "").strip().lower(),
        "issue_kind": str(normalized.get("issue_kind") or "").strip().lower(),
        "issue_reference": str(normalized.get("issue_reference") or "").strip(),
        "settlement_reference": str(normalized.get("settlement_reference") or "").strip(),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()


def _resolve_payment_intent(normalized: dict) -> PaymentIntent | None:
    payment_intent_id = str(normalized.get("payment_intent_id") or "").strip()
    provider_intent_id = str(normalized.get("provider_intent_id") or "").strip()
    external_reference = str(normalized.get("external_reference") or "").strip()
    provider_reference = str(normalized.get("provider_reference") or "").strip()

    if payment_intent_id:
        payment_intent = PaymentIntent.objects.select_for_update().filter(pk=payment_intent_id).first()
        if payment_intent is not None:
            return payment_intent
    if provider_intent_id:
        payment_intent = PaymentIntent.objects.select_for_update().filter(provider_intent_id=provider_intent_id).first()
        if payment_intent is not None:
            return payment_intent
    if external_reference:
        payment_intent = PaymentIntent.objects.select_for_update().filter(external_reference=external_reference).first()
        if payment_intent is not None:
            return payment_intent
    if provider_reference:
        payment_intent = PaymentIntent.objects.select_for_update().filter(provider_reference=provider_reference).first()
        if payment_intent is not None:
            return payment_intent
    return None


@transaction.atomic
def process_payment_provider_callback(*, provider: str, payload: dict, headers: dict | None = None) -> dict:
    provider_payload = payload or {}
    provider_headers = headers or {}
    payload = sanitize_external_payload(provider_payload)
    headers = sanitize_external_payload(provider_headers)
    adapter = get_payment_provider_adapter(provider)
    try:
        normalized = adapter.normalize_callback(provider_payload, headers=provider_headers)
        normalized = sanitize_external_payload(
            json.loads(json.dumps(normalized, sort_keys=True, default=str))
        )
    except PaymentProviderContractError as exc:
        receipt, _created = PaymentProviderCallbackReceipt.objects.get_or_create(
            idempotency_key=_raw_callback_receipt_key(provider, payload or {}, headers=headers or {}),
            defaults={
                "provider": str(provider or "").strip(),
                "callback_type": "contract_error",
                "signature_valid": False,
                "raw_payload": payload or {},
                "normalized_payload": {
                    "provider": str(provider or "").strip(),
                    "contract_error": str(exc),
                    "contract_error_code": getattr(exc, "code", "invalid_provider_contract"),
                },
                "raw_headers": headers or {},
                "status": PaymentProviderCallbackReceipt.Status.FAILED,
                "error_message": str(exc),
            },
        )
        if not _created and receipt.status == PaymentProviderCallbackReceipt.Status.FAILED:
            return {
                "applied": False,
                "duplicate": True,
                "reason": getattr(exc, "code", "invalid_provider_contract"),
                "receipt_id": str(receipt.pk),
            }
        receipt.status = PaymentProviderCallbackReceipt.Status.FAILED
        receipt.error_message = str(exc)
        receipt.processed_at = timezone.now()
        receipt.save(update_fields=["status", "error_message", "processed_at"])
        return {
            "applied": False,
            "reason": getattr(exc, "code", "invalid_provider_contract"),
            "receipt_id": str(receipt.pk),
        }

    payment_intent = _resolve_payment_intent(normalized)

    receipt, _created = PaymentProviderCallbackReceipt.objects.get_or_create(
        idempotency_key=_callback_receipt_key(provider, normalized),
        defaults={
            "provider": str(provider or "").strip(),
            "callback_type": str(normalized.get("callback_type") or "status").strip(),
            "external_reference": str(normalized.get("external_reference") or "").strip()[:128],
            "provider_intent_id": str(normalized.get("provider_intent_id") or "").strip()[:128],
            "provider_reference": str(normalized.get("provider_reference") or "").strip()[:128],
            "payment_intent": payment_intent,
            "signature_valid": bool(normalized.get("signature_valid")),
            "raw_payload": payload or {},
            "normalized_payload": normalized or {},
            "raw_headers": headers or {},
        },
    )

    if not _created and receipt.status == PaymentProviderCallbackReceipt.Status.PROCESSED:
        return {
            "applied": True,
            "duplicate": True,
            "receipt_id": str(receipt.pk),
            "payment_intent_id": str(receipt.payment_intent_id or ""),
        }

    if payment_intent and receipt.payment_intent_id != payment_intent.pk:
        receipt.payment_intent = payment_intent

    if not normalized.get("signature_valid"):
        receipt.status = PaymentProviderCallbackReceipt.Status.FAILED
        receipt.error_message = "Firma o autenticacion de callback invalida."
        receipt.save(update_fields=["payment_intent", "status", "error_message"])
        return {"applied": False, "reason": "invalid_signature", "receipt_id": str(receipt.pk)}

    if payment_intent is not None:
        record_payment_provider_reference(
            payment_intent,
            provider_reference=str(normalized.get("provider_reference") or ""),
            provider_cus=str(normalized.get("provider_cus") or ""),
            provider_metadata=dict(normalized.get("metadata") or {}),
        )

    status_value = str(normalized.get("status") or "").strip().lower()
    issue_kind = str(normalized.get("issue_kind") or "").strip().lower()
    transition_ignored = False
    if payment_intent is not None and status_value:
        if payment_intent.status == status_value:
            transition_ignored = True
            normalized["transition_ignored_reason"] = "already_applied"
        elif not can_apply_provider_transition(payment_intent.status, status_value):
            transition_ignored = True
            normalized["transition_ignored_reason"] = "out_of_order"
        if transition_ignored:
            normalized["transition_from"] = payment_intent.status
            normalized["transition_to"] = status_value

    if payment_intent is not None and not transition_ignored:
        if status_value == "dispatched":
            payment_intent = mark_payment_intent_dispatched(
                payment_intent,
                provider_intent_id=str(normalized.get("provider_intent_id") or ""),
                provider_metadata=dict(normalized.get("metadata") or {}),
            )
        elif status_value == "processing":
            payment_intent = mark_payment_intent_processing(payment_intent, provider_metadata=dict(normalized.get("metadata") or {}))
        elif status_value == "requires_action":
            payment_intent = mark_payment_intent_requires_action(payment_intent, provider_metadata=dict(normalized.get("metadata") or {}))
        elif status_value == "succeeded":
            payment_intent = mark_payment_intent_succeeded(
                payment_intent,
                provider_intent_id=str(normalized.get("provider_intent_id") or ""),
                provider_metadata=dict(normalized.get("metadata") or {}),
            )
        elif status_value == "failed":
            payment_intent = mark_payment_intent_failed(
                payment_intent,
                failure_code=str(normalized.get("failure_code") or ""),
                failure_message=str(normalized.get("failure_message") or ""),
                provider_metadata=dict(normalized.get("metadata") or {}),
            )
        elif status_value == "cancelled":
            payment_intent = mark_payment_intent_cancelled(
                payment_intent,
                failure_message=str(normalized.get("failure_message") or ""),
                provider_metadata=dict(normalized.get("metadata") or {}),
            )
        elif status_value == "settled":
            payment_intent = mark_payment_intent_settled(payment_intent, provider_metadata=dict(normalized.get("metadata") or {}))
            settlement = record_payment_settlement(
                payment_intent=payment_intent,
                provider=payment_intent.provider,
                rail=payment_intent.rail,
                settlement_reference=str(normalized.get("settlement_reference") or ""),
                provider_reference=str(normalized.get("provider_reference") or ""),
                provider_cus=str(normalized.get("provider_cus") or ""),
                amount=normalized.get("amount") or payment_intent.amount,
                settlement_payload=normalized,
            )
            publish_payment_event_after_commit(
                event_type=PaymentDomainEventTypes.PAYMENT_SETTLEMENT_RECORDED,
                payload={
                    "payment_intent_id": str(payment_intent.pk),
                    "settlement_id": str(settlement.pk),
                    "provider": payment_intent.provider,
                    "rail": payment_intent.rail,
                    "amount": str(settlement.amount),
                    "settlement_reference": settlement.settlement_reference,
                },
                metadata={
                    "source": "payments.payment_intents.callback_service",
                    "aggregate_type": "payment",
                    "aggregate_id": str(payment_intent.pk),
                },
                priority=EventPriority.NORMAL,
            )
        elif status_value == "reversed":
            payment_intent = mark_payment_intent_reversed(
                payment_intent,
                failure_message="Reversal reportada por proveedor.",
                provider_metadata=dict(normalized.get("metadata") or {}),
            )
        elif status_value == "disputed":
            payment_intent = mark_payment_intent_disputed(
                payment_intent,
                failure_message="Dispute reportada por proveedor.",
                provider_metadata=dict(normalized.get("metadata") or {}),
            )

    if issue_kind in {PaymentOperationalCase.Kind.REVERSAL, PaymentOperationalCase.Kind.DISPUTE, PaymentOperationalCase.Kind.REFUND}:
        case = open_payment_operational_case(
            payment_intent=payment_intent,
            provider=str(provider or "").strip(),
            kind=issue_kind,
            amount=normalized.get("amount") or Decimal("0"),
            currency=str(normalized.get("currency") or "COP"),
            provider_reference=str(normalized.get("provider_reference") or ""),
            provider_case_reference=str(normalized.get("issue_reference") or ""),
            details=normalized,
        )
        if payment_intent is not None:
            if issue_kind == PaymentOperationalCase.Kind.REVERSAL:
                if can_apply_provider_transition(payment_intent.status, PaymentIntent.Status.REVERSED):
                    payment_intent = mark_payment_intent_reversed(
                        payment_intent,
                        failure_message=f"Reversal reportada por proveedor. Caso={case.pk}",
                        provider_metadata=dict(normalized.get("metadata") or {}),
                    )
            elif issue_kind == PaymentOperationalCase.Kind.DISPUTE:
                if can_apply_provider_transition(payment_intent.status, PaymentIntent.Status.DISPUTED):
                    payment_intent = mark_payment_intent_disputed(
                        payment_intent,
                        failure_message=f"Dispute reportada por proveedor. Caso={case.pk}",
                        provider_metadata=dict(normalized.get("metadata") or {}),
                    )

    receipt.status = PaymentProviderCallbackReceipt.Status.PROCESSED
    receipt.processed_at = timezone.now()
    receipt.normalized_payload = normalized or {}
    receipt.save(update_fields=["payment_intent", "status", "processed_at", "normalized_payload"])

    publish_payment_event_after_commit(
        event_type=PaymentDomainEventTypes.PAYMENT_CALLBACK_RECEIVED,
        payload={
            "provider": str(provider or "").strip(),
            "receipt_id": str(receipt.pk),
            "payment_intent_id": str(getattr(payment_intent, "pk", "") or ""),
            "status": status_value,
            "issue_kind": issue_kind,
            "callback_type": str(normalized.get("callback_type") or ""),
            "provider_event_type": str(normalized.get("provider_event_type") or ""),
            "contract_version": str(normalized.get("contract_version") or ""),
        },
        metadata={
            "source": "payments.payment_intents.callback_service",
            "aggregate_type": "payment_callback",
            "aggregate_id": str(receipt.pk),
        },
        priority=EventPriority.LOW,
    )

    return {
        "applied": True,
        "receipt_id": str(receipt.pk),
        "payment_intent_id": str(getattr(payment_intent, "pk", "") or ""),
        "status": status_value,
        "issue_kind": issue_kind,
        "transition_ignored": transition_ignored,
    }
