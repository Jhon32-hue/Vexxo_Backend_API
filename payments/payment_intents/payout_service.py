"""
Servicios base para dispersiones/lotes de pagos.

La ejecucion real del rail puede llegar despues; este modulo deja la
semantica del dominio y el pricing desde ya.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import transaction

from common.domain_events import EventPriority
from identity.users.services.product_access_service import validate_payout_allowed
from payments.payment_intents.domain_events import PaymentDomainEventTypes
from payments.payment_intents.event_service import publish_payment_event_after_commit
from payments.payment_intents.models import PayoutBatch, PayoutInstruction
from payments.payment_intents.pricing_service import calculate_payout_pricing


def _payout_batch_key(*, user, provider: str, currency: str, instructions: list[dict]) -> str:
    raw = json.dumps(
        {
            "owner_id": str(user.pk),
            "provider": str(provider or "").strip(),
            "currency": str(currency or "").strip().upper(),
            "instructions": instructions,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _payout_instruction_transition(*, before_counted: bool, after_counted: bool, amount) -> dict:
    return {
        "before_counted": bool(before_counted),
        "after_counted": bool(after_counted),
        "amount": str(amount),
    }


@transaction.atomic
def create_payout_batch(*, user, provider: str, rail: str, currency: str = "COP", instructions: list[dict] | None = None):
    normalized_instructions = list(instructions or [])
    total_amount = sum((Decimal(str(item.get("amount") or "0")) for item in normalized_instructions), Decimal("0.00"))
    for item in normalized_instructions:
        validate_payout_allowed(
            user,
            amount=item.get("amount") or 0,
            provider=provider,
            rail=rail,
            source="payments.payment_intents.payout_service.create_payout_batch",
        )
    batch, created = PayoutBatch.objects.get_or_create(
        idempotency_key=_payout_batch_key(user=user, provider=provider, currency=currency, instructions=normalized_instructions),
        defaults={
            "owner": user,
            "provider": provider,
            "rail": rail,
            "currency": str(currency or "COP").upper(),
            "total_instructions": len(normalized_instructions),
            "total_amount": total_amount,
            "pricing_snapshot": {
                "instructions_requested": len(normalized_instructions),
                "requested_total_amount": str(total_amount),
            },
        },
    )
    if created:
        publish_payment_event_after_commit(
            event_type=PaymentDomainEventTypes.PAYMENT_PAYOUT_REQUESTED,
            payload={
                "batch_id": str(batch.pk),
                "owner_id": str(batch.owner_id),
                "provider": batch.provider,
                "rail": batch.rail,
                "currency": batch.currency,
                "total_instructions": batch.total_instructions,
                "total_amount": str(batch.total_amount),
            },
            metadata={
                "source": "payments.payment_intents.payout_service.create_payout_batch",
                "projection_event_key": f"payout-batch:{batch.pk}:requested",
            },
            priority=EventPriority.NORMAL,
        )
    return batch


@transaction.atomic
def add_payout_instruction(
    *,
    batch: PayoutBatch,
    beneficiary_name: str,
    beneficiary_account_ref: str,
    amount,
    beneficiary_document: str = "",
    external_reference: str = "",
):
    validate_payout_allowed(
        batch.owner,
        amount=amount,
        provider=batch.provider,
        rail=batch.rail,
        source="payments.payment_intents.payout_service.add_payout_instruction",
    )
    pricing = calculate_payout_pricing(
        user=batch.owner,
        amount=amount,
        provider=batch.provider,
        rail=batch.rail,
    )
    instruction = PayoutInstruction.objects.create(
        batch=batch,
        beneficiary_name=beneficiary_name,
        beneficiary_document=beneficiary_document,
        beneficiary_account_ref=beneficiary_account_ref,
        amount=Decimal(str(amount)),
        currency=batch.currency,
        external_reference=external_reference,
        fee_breakdown=pricing.get("breakdown", {}).get("vexxo", {}),
        tax_breakdown={
            "provider_tax": pricing.get("provider_tax", "0.00"),
            "vexxo_tax": pricing.get("vexxo_tax", "0.00"),
            "tax_cost": pricing.get("tax_cost", "0.00"),
        },
    )
    batch.total_instructions = batch.instructions.count()
    batch.total_amount = sum((item.amount for item in batch.instructions.all()), Decimal("0.00"))
    batch.pricing_snapshot = {
        **(batch.pricing_snapshot or {}),
        "instructions_requested": int(batch.total_instructions or 0),
        "requested_total_amount": str(batch.total_amount),
    }
    batch.save(update_fields=["total_instructions", "total_amount", "pricing_snapshot", "updated_at"])
    publish_payment_event_after_commit(
        event_type=PaymentDomainEventTypes.PAYMENT_PAYOUT_REQUESTED,
        payload={
            "instruction_id": str(instruction.pk),
            "batch_id": str(batch.pk),
            "owner_id": str(batch.owner_id),
            "provider": batch.provider,
            "rail": batch.rail,
            "amount": str(instruction.amount),
            "currency": instruction.currency,
            "beneficiary_name": instruction.beneficiary_name,
            "external_reference": instruction.external_reference,
            "usage_transition": _payout_instruction_transition(
                before_counted=False,
                after_counted=True,
                amount=instruction.amount,
            ),
        },
        metadata={
            "source": "payments.payment_intents.payout_service.add_payout_instruction",
            "projection_event_key": f"payout-instruction:{instruction.pk}:requested",
        },
    )
    return instruction


@transaction.atomic
def mark_payout_instruction_succeeded(instruction: PayoutInstruction, *, provider_reference: str = "", provider_cus: str = ""):
    instruction.status = PayoutInstruction.Status.SUCCEEDED
    instruction.provider_reference = str(provider_reference or "")[:128]
    instruction.provider_cus = str(provider_cus or "")[:64]
    instruction.save(update_fields=["status", "provider_reference", "provider_cus", "updated_at"])
    publish_payment_event_after_commit(
        event_type=PaymentDomainEventTypes.PAYMENT_PAYOUT_SUCCEEDED,
        payload={
            "instruction_id": str(instruction.pk),
            "batch_id": str(instruction.batch_id),
            "owner_id": str(instruction.batch.owner_id),
            "amount": str(instruction.amount),
            "currency": instruction.currency,
            "beneficiary_name": instruction.beneficiary_name,
            "provider_reference": instruction.provider_reference,
            "provider_cus": instruction.provider_cus,
            "usage_transition": _payout_instruction_transition(
                before_counted=True,
                after_counted=True,
                amount=instruction.amount,
            ),
        },
        metadata={
            "source": "payments.payment_intents.payout_service.mark_payout_instruction_succeeded",
            "projection_event_key": f"payout-instruction:{instruction.pk}:succeeded",
        },
    )
    return instruction


@transaction.atomic
def mark_payout_instruction_failed(instruction: PayoutInstruction, *, failure_code: str = "", failure_message: str = ""):
    instruction.status = PayoutInstruction.Status.FAILED
    instruction.failure_code = str(failure_code or "")[:64]
    instruction.failure_message = str(failure_message or "")[:2000]
    instruction.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
    publish_payment_event_after_commit(
        event_type=PaymentDomainEventTypes.PAYMENT_PAYOUT_FAILED,
        payload={
            "instruction_id": str(instruction.pk),
            "batch_id": str(instruction.batch_id),
            "owner_id": str(instruction.batch.owner_id),
            "amount": str(instruction.amount),
            "currency": instruction.currency,
            "beneficiary_name": instruction.beneficiary_name,
            "failure_code": instruction.failure_code,
            "failure_message": instruction.failure_message,
            "usage_transition": _payout_instruction_transition(
                before_counted=True,
                after_counted=False,
                amount=instruction.amount,
            ),
        },
        metadata={
            "source": "payments.payment_intents.payout_service.mark_payout_instruction_failed",
            "projection_event_key": f"payout-instruction:{instruction.pk}:failed",
        },
    )
    return instruction
