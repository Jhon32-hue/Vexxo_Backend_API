"""
Servicios de planificacion de pagos recurrentes o programados.

Este bounded context no ejecuta el pago; prepara templates y corridas que luego
generan un `PaymentIntent`.
"""

from __future__ import annotations

import hashlib
import json

from django.db import transaction

from payments.payment_intents.domain_events import PaymentDomainEventTypes
from payments.payment_intents.event_service import publish_payment_event_after_commit
from payments.payment_intents.models import PaymentIntent
from payments.payment_intents.services import create_payment_intent
from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate


def _schedule_run_key(*, template: PaymentTemplate, scheduled_for, payload: dict | None = None) -> str:
    raw = json.dumps(
        {
            "template_id": template.pk,
            "scheduled_for": str(scheduled_for),
            "payload": payload or {},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_payment_template(**validated_data):
    template = PaymentTemplate.objects.create(**validated_data)
    publish_payment_event_after_commit(
        event_type=PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_CREATED,
        payload={
            "template_id": str(template.pk),
            "owner_id": str(template.owner_id),
            "payment_type": template.payment_type,
            "cadence": template.cadence,
            "is_active": template.is_active,
        },
        metadata={"source": "payments.scheduled_payments.services.create_payment_template"},
    )
    return template


def update_payment_template(template: PaymentTemplate, **changes):
    for field, value in changes.items():
        setattr(template, field, value)
    template.save()
    publish_payment_event_after_commit(
        event_type=PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_UPDATED,
        payload={
            "template_id": str(template.pk),
            "owner_id": str(template.owner_id),
            "payment_type": template.payment_type,
            "cadence": template.cadence,
            "is_active": template.is_active,
        },
        metadata={"source": "payments.scheduled_payments.services.update_payment_template"},
    )
    return template


def request_payment_schedule_run(*, template: PaymentTemplate, scheduled_for, run_payload: dict | None = None):
    run, _created = PaymentScheduleRun.objects.get_or_create(
        idempotency_key=_schedule_run_key(template=template, scheduled_for=scheduled_for, payload=run_payload),
        defaults={
            "owner": template.owner,
            "template": template,
            "scheduled_for": scheduled_for,
            "run_payload": run_payload or {},
        },
    )
    publish_payment_event_after_commit(
        event_type=PaymentDomainEventTypes.PAYMENT_RECURRING_RUN_REQUESTED,
        payload={
            "schedule_run_id": str(run.pk),
            "template_id": str(template.pk),
            "owner_id": str(template.owner_id),
            "scheduled_for": run.scheduled_for.isoformat(),
            "payment_type": template.payment_type,
        },
        metadata={"source": "payments.scheduled_payments.services.request_payment_schedule_run"},
    )
    return run


@transaction.atomic
def create_payment_intent_from_schedule_run(
    run: PaymentScheduleRun,
    *,
    amount=None,
    provider: str = "",
    rail: str = "",
):
    """
    Materializa un `PaymentIntent` desde una corrida programada.

    La corrida sigue siendo planificacion; el intent es la frontera de
    ejecucion externa real.
    """
    if run.payment_intent_id:
        return run.payment_intent

    template = run.template
    resolved_amount = amount if amount is not None else template.default_amount
    if resolved_amount is None:
        raise ValueError("PaymentTemplate variable requiere amount explicito para generar PaymentIntent.")

    execution_defaults = dict(template.execution_defaults or {})
    intent = create_payment_intent(
        user=template.owner,
        account=template.account,
        category=template.category,
        vendor=template.vendor,
        amount=resolved_amount,
        currency=template.currency,
        provider=str(provider or execution_defaults.get("provider") or "").strip() or "generic",
        payment_type=PaymentIntent.PaymentType.SCHEDULED,
        rail=str(rail or execution_defaults.get("rail") or "").strip() or PaymentIntent.Rail.OTHER,
        beneficiary_name=template.beneficiary_name,
        beneficiary_document=template.beneficiary_document,
        beneficiary_account_ref=template.beneficiary_account_ref,
        external_reference=template.external_reference,
        invoice_reference=str(execution_defaults.get("invoice_reference") or "").strip(),
        source="payments.scheduled_payments.services.create_payment_intent_from_schedule_run",
        idempotency_key=f"schedule-run:{run.pk}",
    )
    run.payment_intent = intent
    run.status = PaymentScheduleRun.Status.PROCESSING
    run.save(update_fields=["payment_intent", "status", "updated_at"])
    return intent


def create_template_from_payment_intent(payment_intent, *, cadence: str = PaymentTemplate.Cadence.MONTHLY, interval_count: int = 1):
    template = create_payment_template(
        owner=payment_intent.owner,
        account=payment_intent.account,
        category=payment_intent.category,
        vendor=payment_intent.vendor,
        name=payment_intent.beneficiary_name or payment_intent.external_reference or f"Pago {payment_intent.provider}",
        payment_type=payment_intent.payment_type,
        amount_mode=PaymentTemplate.AmountMode.FIXED,
        default_amount=payment_intent.amount,
        currency=payment_intent.currency,
        cadence=cadence,
        interval_count=max(1, int(interval_count or 1)),
        beneficiary_name=payment_intent.beneficiary_name,
        beneficiary_document=payment_intent.beneficiary_document,
        beneficiary_account_ref=payment_intent.beneficiary_account_ref,
        external_reference=payment_intent.external_reference,
        execution_defaults={
            "provider": payment_intent.provider,
            "rail": payment_intent.rail,
            "invoice_reference": payment_intent.invoice_reference,
        },
    )
    return template
