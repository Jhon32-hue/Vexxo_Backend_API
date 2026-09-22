"""
Servicios de planificacion de pagos recurrentes o programados.

Este bounded context no ejecuta el pago; prepara templates y corridas que luego
generan un `PaymentIntent`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from finance.budgets.attribution import BudgetAttributionSource
from finance.budgets.attribution_service import resolve_budget_attribution
from finance.transactions.Models.transacciones import Transaction
from finance.transactions.transaction_write_service import create_manual_transaction
from notifications.deliveries.services import create_notification_delivery
from payments.payment_intents.domain_events import PaymentDomainEventTypes
from payments.payment_intents.event_service import publish_payment_event_after_commit
from payments.payment_intents.models import PaymentIntent
from payments.payment_intents.services import create_payment_intent
from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate
from payments.scheduled_payments.realtime_services import publish_schedule_run_signal


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


TERMINAL_RUN_STATUSES = {
    PaymentScheduleRun.Status.PAID,
    PaymentScheduleRun.Status.PAID_OUTSIDE_VEXXO,
    PaymentScheduleRun.Status.SKIPPED,
    PaymentScheduleRun.Status.CANCELED,
    PaymentScheduleRun.Status.FAILED,
}

MANUAL_RESOLUTION_BLOCKING_INTENT_STATUSES = {
    PaymentIntent.Status.CREATED,
    PaymentIntent.Status.DISPATCHED,
    PaymentIntent.Status.PROCESSING,
    PaymentIntent.Status.REQUIRES_ACTION,
    PaymentIntent.Status.SUCCEEDED,
    PaymentIntent.Status.SETTLED,
    PaymentIntent.Status.REVERSED,
    PaymentIntent.Status.DISPUTED,
}

TEMPLATE_MUTABLE_RUN_BLOCKING_STATUSES = {
    PaymentScheduleRun.Status.PROCESSING,
}


def _normalize_due_on(*, scheduled_for, due_on=None):
    if due_on is not None:
        return due_on
    if scheduled_for is None:
        return None
    return getattr(scheduled_for, "date", lambda: scheduled_for)()


def _run_reference(run: PaymentScheduleRun) -> str:
    due_label = run.due_on.isoformat() if run.due_on else str(run.scheduled_for.date())
    return f"{run.template.name} ({due_label})"


def _run_payload(run: PaymentScheduleRun) -> dict:
    return {
        "schedule_run_id": str(run.pk),
        "template_id": str(run.template_id),
        "payment_intent_id": str(run.payment_intent_id or ""),
        "materialized_transaction_id": str(run.materialized_transaction_id or ""),
        "status": run.status,
        "due_on": run.due_on.isoformat() if run.due_on else "",
        "expected_amount": str(run.expected_amount) if run.expected_amount is not None else "",
        "expected_currency": run.expected_currency,
        "paid_at": run.paid_at.isoformat() if run.paid_at else "",
        "postponed_until": run.postponed_until.isoformat() if run.postponed_until else "",
        "resolution_action": run.resolution_action,
    }


def _manual_resolution_is_blocked(run: PaymentScheduleRun) -> bool:
    if not run.payment_intent_id:
        return False
    intent_status = getattr(run.payment_intent, "status", "")
    return intent_status in MANUAL_RESOLUTION_BLOCKING_INTENT_STATUSES


def _run_is_mutable_from_template(run: PaymentScheduleRun | None) -> bool:
    if run is None:
        return False
    if run.status in TERMINAL_RUN_STATUSES or run.status in TEMPLATE_MUTABLE_RUN_BLOCKING_STATUSES:
        return False
    if run.payment_intent_id or run.materialized_transaction_id:
        return False
    return True


def _assert_manual_resolution_allowed(run: PaymentScheduleRun, *, action_label: str) -> None:
    if not _manual_resolution_is_blocked(run):
        return
    raise ValueError(
        f"No puedes {action_label} esta ocurrencia mientras exista un PaymentIntent activo o ya liquidado. "
        "Cancela o resuelve primero el flujo de pago externo."
    )


def _sync_scheduled_payments_projection(owner_id, *, source: str):
    from identity.users.services.product_usage_projection_service import sync_scheduled_payments_slice

    sync_scheduled_payments_slice(owner_id, source=source)


def _sync_mutable_run_from_template(
    run: PaymentScheduleRun | None,
    *,
    template: PaymentTemplate,
    changed_fields: set[str] | None = None,
) -> PaymentScheduleRun | None:
    if not _run_is_mutable_from_template(run):
        return run
    changed_fields = changed_fields or set()
    updated_fields = []
    if ("next_run_at" in changed_fields or run.due_on is None) and template.next_run_at is not None:
        run.scheduled_for = template.next_run_at
        run.due_on = template.next_run_at.date()
        run.postponed_until = None
        run.reminder_stage = 0
        updated_fields.extend(["scheduled_for", "due_on", "postponed_until", "reminder_stage"])
    if template.default_amount is not None and ("default_amount" in changed_fields or run.expected_amount is None):
        run.expected_amount = template.default_amount
        updated_fields.append("expected_amount")
    if ("currency" in changed_fields or not run.expected_currency) and template.currency:
        run.expected_currency = template.currency
        updated_fields.append("expected_currency")
    if updated_fields:
        _sync_run_status_from_dates(run)
        updated_fields.extend(["status", "updated_at"])
        run.save(update_fields=list(dict.fromkeys(updated_fields)))
    return run


def _sync_run_status_from_dates(run: PaymentScheduleRun, *, as_of_date=None) -> PaymentScheduleRun:
    as_of_date = as_of_date or timezone.localdate()
    if run.status in TERMINAL_RUN_STATUSES or run.status == PaymentScheduleRun.Status.PROCESSING:
        return run
    if run.postponed_until and run.postponed_until > as_of_date:
        if run.status != PaymentScheduleRun.Status.POSTPONED:
            run.status = PaymentScheduleRun.Status.POSTPONED
        return run
    due_on = run.due_on or _normalize_due_on(scheduled_for=run.scheduled_for)
    if due_on is None:
        return run
    if due_on > as_of_date:
        run.status = PaymentScheduleRun.Status.SCHEDULED
        return run
    if due_on == as_of_date:
        run.status = PaymentScheduleRun.Status.DUE
        return run
    run.status = PaymentScheduleRun.Status.OVERDUE
    return run


def _reminder_stage_for(run: PaymentScheduleRun, *, as_of_date) -> int:
    due_on = run.due_on or _normalize_due_on(scheduled_for=run.scheduled_for)
    if due_on is None or run.status not in {PaymentScheduleRun.Status.DUE, PaymentScheduleRun.Status.OVERDUE}:
        return 0
    days_late = (as_of_date - due_on).days
    if days_late < 0:
        return 0
    if days_late > 3:
        return 0
    return days_late + 1


def _create_run_notification(run: PaymentScheduleRun, *, stage: int, as_of_date) -> None:
    title = f"Pago programado pendiente: {run.template.name}"
    if stage == 1:
        message = f"Hoy vence {run.template.name}. Confirma si ya lo pagaste o posponlo."
        event_type = "payments.scheduled.run.due"
        realtime_event = "payment.schedule_run.due"
    else:
        days = stage - 1
        message = f"{run.template.name} sigue pendiente desde hace {days} dia(s). Confirma si ya lo pagaste."
        event_type = "payments.scheduled.run.overdue"
        realtime_event = "payment.schedule_run.overdue"
    payload = {
        **_run_payload(run),
        "reminder_stage": stage,
        "as_of_date": as_of_date.isoformat(),
        "available_actions": [
            "mark_paid",
            "mark_paid_outside_vexxo",
            "postpone",
            "skip",
            "pay_with_vexxo",
        ],
    }
    create_notification_delivery(
        owner=run.owner,
        title=title,
        message=message,
        event_type=event_type,
        source="payments.scheduled_payments.services.process_due_schedule_runs",
        payload=payload,
        dedupe_key=f"payment-schedule-run:{run.pk}:stage:{stage}",
    )
    publish_schedule_run_signal(
        owner_id=run.owner_id,
        schedule_run_id=run.pk,
        event=realtime_event,
        extra=payload,
    )
    run.reminder_stage = max(run.reminder_stage, stage)
    run.reminder_count = max(run.reminder_count, stage)
    run.last_reminded_at = timezone.now()


def _resolve_run_amount(run: PaymentScheduleRun, *, amount=None) -> Decimal:
    resolved = amount if amount is not None else run.expected_amount or run.template.default_amount
    if resolved is None:
        raise ValueError("El pago programado no tiene monto resuelto.")
    return Decimal(str(resolved))


def _ensure_template_open_run(template: PaymentTemplate) -> PaymentScheduleRun | None:
    if not template.is_active or not template.next_run_at:
        return None
    open_runs = list(
        PaymentScheduleRun.objects.filter(template=template)
        .exclude(status__in=list(TERMINAL_RUN_STATUSES))
        .order_by("scheduled_for", "id")
    )
    target_key = _schedule_run_key(template=template, scheduled_for=template.next_run_at, payload={"origin": "template_bootstrap"})
    target_run = next((run for run in open_runs if run.idempotency_key == target_key), None)
    blocking_run = None
    for existing_run in open_runs:
        if target_run is not None and existing_run.pk == target_run.pk:
            continue
        if existing_run.payment_intent_id or existing_run.materialized_transaction_id or existing_run.status == PaymentScheduleRun.Status.PROCESSING:
            blocking_run = existing_run
            continue
        existing_run.status = PaymentScheduleRun.Status.CANCELED
        existing_run.resolved_at = timezone.now()
        existing_run.resolution_action = PaymentScheduleRun.ResolutionAction.CANCEL
        existing_run.resolution_note = "Superseded by template schedule update."
        existing_run.save(
            update_fields=[
                "status",
                "resolved_at",
                "resolution_action",
                "resolution_note",
                "updated_at",
            ]
        )
    if target_run is None and blocking_run is not None:
        return blocking_run
    run, _created = PaymentScheduleRun.objects.get_or_create(
        idempotency_key=target_key,
        defaults={
            "owner": template.owner,
            "template": template,
            "scheduled_for": template.next_run_at,
            "due_on": template.next_run_at.date(),
            "expected_amount": template.default_amount,
            "expected_currency": template.currency,
            "status": PaymentScheduleRun.Status.SCHEDULED,
            "run_payload": {"origin": "template_bootstrap"},
        },
    )
    missing_updates = []
    if run.due_on is None:
        run.due_on = template.next_run_at.date()
        missing_updates.append("due_on")
    if run.expected_amount is None and template.default_amount is not None:
        run.expected_amount = template.default_amount
        missing_updates.append("expected_amount")
    if not run.expected_currency:
        run.expected_currency = template.currency
        missing_updates.append("expected_currency")
    if missing_updates:
        missing_updates.append("updated_at")
        run.save(update_fields=missing_updates)
    return run


def _serialize_template_state(template: PaymentTemplate | None) -> dict:
    if template is None:
        return {}
    return {
        "template_id": str(template.pk),
        "owner_id": str(template.owner_id),
        "category_id": str(template.category_id or ""),
        "budget_scope": str(template.budget_scope or ""),
        "shared_budget_id": str(template.shared_budget_id or ""),
        "budget_attribution_source": str(template.budget_attribution_source or ""),
        "payment_type": template.payment_type,
        "amount_mode": template.amount_mode,
        "default_amount": str(template.default_amount) if template.default_amount is not None else "",
        "currency": template.currency,
        "next_run_at": template.next_run_at.isoformat() if template.next_run_at else "",
        "is_active": bool(template.is_active),
        "cadence": template.cadence,
    }


def _template_changed_fields(before: dict, after: dict) -> list[str]:
    tracked = [
        "category_id",
        "budget_scope",
        "shared_budget_id",
        "budget_attribution_source",
        "payment_type",
        "amount_mode",
        "default_amount",
        "currency",
        "next_run_at",
        "is_active",
        "cadence",
    ]
    return [field for field in tracked if str(before.get(field, "")) != str(after.get(field, ""))]


def _publish_template_event(*, template: PaymentTemplate, event_type: str, source: str, before: dict | None = None):
    after = _serialize_template_state(template)
    payload = {
        "template_id": str(template.pk),
        "owner_id": str(template.owner_id),
        "category_id": str(template.category_id or ""),
        "budget_scope": str(template.budget_scope or ""),
        "shared_budget_id": str(template.shared_budget_id or ""),
        "budget_attribution_source": str(template.budget_attribution_source or ""),
        "payment_type": template.payment_type,
        "amount_mode": template.amount_mode,
        "default_amount": str(template.default_amount) if template.default_amount is not None else "",
        "currency": template.currency,
        "next_run_at": template.next_run_at.isoformat() if template.next_run_at else "",
        "is_active": bool(template.is_active),
        "cadence": template.cadence,
        "before": before or {},
        "after": after,
        "changed_fields": _template_changed_fields(before or {}, after),
    }
    publish_payment_event_after_commit(
        event_type=event_type,
        payload=payload,
        metadata={
            "source": source,
            "aggregate_type": "payment_template",
            "aggregate_id": str(template.pk),
        },
    )


def create_payment_template(**validated_data):
    skip_limit_validation = bool(validated_data.pop("_skip_limit_validation", False))
    idempotency_key = str(validated_data.pop("idempotency_key", "") or "").strip()
    budget_context_shared_budget = validated_data.pop("budget_context_shared_budget", None)
    category = validated_data.get("category")
    if idempotency_key:
        existing = PaymentTemplate.objects.filter(
            owner=validated_data.get("owner"), idempotency_key=idempotency_key
        ).first()
        if existing:
            comparable = {
                "name": str(validated_data.get("name") or "").strip(),
                "default_amount": str(validated_data.get("default_amount") or ""),
                "currency": str(validated_data.get("currency") or "COP"),
                "account_id": getattr(validated_data.get("account"), "pk", None),
            }
            current = {
                "name": existing.name,
                "default_amount": str(existing.default_amount or ""),
                "currency": existing.currency,
                "account_id": existing.account_id,
            }
            if comparable != current:
                raise ValueError("Idempotency-Key ya fue usada con otro pago programado.")
            existing._idempotent_replay = True
            return existing
    if not skip_limit_validation and validated_data.get("is_active", True):
        from identity.users.services.product_access_service import validate_scheduled_payments_limit

        validate_scheduled_payments_limit(
            validated_data.get("owner"),
            source="payments.scheduled_payments.create_payment_template",
        )
    attribution = resolve_budget_attribution(
        user=validated_data.get("owner"),
        budget_scope=validated_data.get("budget_scope"),
        shared_budget=validated_data.get("shared_budget"),
        budget_context_shared_budget=budget_context_shared_budget,
        current_scope="",
        current_shared_budget=None,
        current_source="",
        expense_expected=True,
    )
    validated_data["budget_scope"] = attribution["budget_scope"]
    validated_data["shared_budget"] = attribution["shared_budget"]
    validated_data["budget_attribution_source"] = attribution["budget_attribution_source"]
    validated_data["idempotency_key"] = idempotency_key
    template = PaymentTemplate.objects.create(**validated_data)
    template._idempotent_replay = False
    _ensure_template_open_run(template)
    _publish_template_event(
        template=template,
        event_type=PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_CREATED,
        source="payments.scheduled_payments.services.create_payment_template",
        before={},
    )
    _sync_scheduled_payments_projection(
        template.owner_id,
        source="payments.scheduled_payments.services.create_payment_template",
    )
    return template


def update_payment_template(template: PaymentTemplate, **changes):
    skip_limit_validation = bool(changes.pop("_skip_limit_validation", False))
    budget_context_shared_budget = changes.pop("budget_context_shared_budget", None)
    before = _serialize_template_state(template)
    if not skip_limit_validation and not before.get("is_active") and bool(changes.get("is_active")):
        from identity.users.services.product_access_service import validate_scheduled_payments_limit

        validate_scheduled_payments_limit(
            template.owner,
            source="payments.scheduled_payments.update_payment_template.activate",
        )
    raw_budget_scope = changes.get("budget_scope") if "budget_scope" in changes else None
    raw_shared_budget = changes.get("shared_budget") if "shared_budget" in changes else None
    explicit_budget_attribution_source = changes.get("budget_attribution_source")
    for field, value in changes.items():
        setattr(template, field, value)
    attribution = resolve_budget_attribution(
        user=template.owner,
        budget_scope=raw_budget_scope,
        shared_budget=raw_shared_budget,
        budget_context_shared_budget=budget_context_shared_budget,
        current_scope=before.get("budget_scope", ""),
        current_shared_budget=getattr(template, "shared_budget", None),
        current_source=before.get("budget_attribution_source", ""),
        expense_expected=True,
    )
    template.budget_scope = attribution["budget_scope"]
    template.shared_budget = attribution["shared_budget"]
    template.budget_attribution_source = explicit_budget_attribution_source or attribution["budget_attribution_source"]
    template.save()
    template.refresh_from_db()
    changed_fields = set(_template_changed_fields(before, _serialize_template_state(template)))
    target_run = _ensure_template_open_run(template)
    _sync_mutable_run_from_template(target_run, template=template, changed_fields=changed_fields)
    _publish_template_event(
        template=template,
        event_type=PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_UPDATED,
        source="payments.scheduled_payments.services.update_payment_template",
        before=before,
    )
    if before.get("is_active") != bool(template.is_active):
        _publish_template_event(
            template=template,
            event_type=(
                PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_ACTIVATED
                if template.is_active
                else PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_DEACTIVATED
            ),
            source="payments.scheduled_payments.services.update_payment_template.lifecycle",
            before=before,
        )
    _sync_scheduled_payments_projection(
        template.owner_id,
        source="payments.scheduled_payments.services.update_payment_template",
    )
    return template


def delete_payment_template(template: PaymentTemplate):
    before = _serialize_template_state(template)
    payload = {
        "template_id": str(template.pk),
        "owner_id": str(template.owner_id),
        "category_id": str(template.category_id or ""),
        "budget_scope": str(template.budget_scope or ""),
        "shared_budget_id": str(template.shared_budget_id or ""),
        "budget_attribution_source": str(template.budget_attribution_source or ""),
        "payment_type": template.payment_type,
        "amount_mode": template.amount_mode,
        "default_amount": str(template.default_amount) if template.default_amount is not None else "",
        "next_run_at": template.next_run_at.isoformat() if template.next_run_at else "",
        "is_active": bool(template.is_active),
        "cadence": template.cadence,
        "before": before,
        "after": {},
        "changed_fields": list(before.keys()),
    }
    with transaction.atomic():
        publish_payment_event_after_commit(
            event_type=PaymentDomainEventTypes.PAYMENT_RECURRING_TEMPLATE_DELETED,
            payload=payload,
            metadata={
                "source": "payments.scheduled_payments.services.delete_payment_template",
                "aggregate_type": "payment_template",
                "aggregate_id": str(template.pk),
            },
        )
        template.delete()
    _sync_scheduled_payments_projection(
        before.get("owner_id"),
        source="payments.scheduled_payments.services.delete_payment_template",
    )


def request_payment_schedule_run(*, template: PaymentTemplate, scheduled_for, run_payload: dict | None = None):
    run, _created = PaymentScheduleRun.objects.get_or_create(
        idempotency_key=_schedule_run_key(template=template, scheduled_for=scheduled_for, payload=run_payload),
        defaults={
            "owner": template.owner,
            "template": template,
            "scheduled_for": scheduled_for,
            "due_on": _normalize_due_on(scheduled_for=scheduled_for),
            "expected_amount": template.default_amount,
            "expected_currency": template.currency,
            "status": PaymentScheduleRun.Status.SCHEDULED,
            "run_payload": run_payload or {},
        },
    )
    updated_fields = []
    if run.due_on is None:
        run.due_on = _normalize_due_on(scheduled_for=scheduled_for)
        updated_fields.append("due_on")
    if run.expected_amount is None and template.default_amount is not None:
        run.expected_amount = template.default_amount
        updated_fields.append("expected_amount")
    if not run.expected_currency:
        run.expected_currency = template.currency
        updated_fields.append("expected_currency")
    if updated_fields:
        updated_fields.append("updated_at")
        run.save(update_fields=updated_fields)
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
    if run.status in TERMINAL_RUN_STATUSES:
        raise ValueError("La ocurrencia ya esta cerrada y no puede generar un PaymentIntent.")

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
        source="payments.scheduled_payments.run_intent",
        idempotency_key=f"schedule-run:{run.pk}",
    )
    run.payment_intent = intent
    run.status = PaymentScheduleRun.Status.PROCESSING
    run.save(update_fields=["payment_intent", "status", "updated_at"])
    return intent


@transaction.atomic
def mark_schedule_run_paid(
    run: PaymentScheduleRun,
    *,
    actor=None,
    paid_on=None,
    amount=None,
    notes: str = "",
    paid_outside_vexxo: bool = False,
) -> PaymentScheduleRun:
    run = PaymentScheduleRun.objects.select_related("template", "payment_intent").get(pk=run.pk)
    if run.status in TERMINAL_RUN_STATUSES:
        return run
    _assert_manual_resolution_allowed(
        run,
        action_label="marcar como pagada manualmente" if not paid_outside_vexxo else "marcar como pagada fuera de Vexxo",
    )
    resolved_paid_on = paid_on or timezone.localdate()
    resolved_amount = _resolve_run_amount(run, amount=amount)
    if run.materialized_transaction_id is None:
        tx = create_manual_transaction(
            validated_data={
                "owner": run.owner,
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": resolved_amount,
                "date": resolved_paid_on,
                "account": run.template.account,
                "category": run.template.category,
                "vendor": run.template.vendor,
                "debt": run.template.debt,
                "installment": run.template.installment,
                "source": "scheduled_payment",
                "notes": notes or f"Pago programado confirmado: {run.template.name}",
                "confirmed": True,
                "budget_scope": run.template.budget_scope,
                "shared_budget": run.template.shared_budget,
                "budget_attribution_source": BudgetAttributionSource.INHERITED_FROM_TEMPLATE,
                "payment_schedule_run": run,
                "raw_payload": {
                    "payment_schedule_run_id": str(run.pk),
                    "payment_template_id": str(run.template_id),
                    "paid_outside_vexxo": bool(paid_outside_vexxo),
                },
            },
            actor=actor,
            event_source="payments.scheduled_payments.services.mark_schedule_run_paid",
        )
        run.materialized_transaction = tx
    run.paid_at = resolved_paid_on
    run.resolved_at = timezone.now()
    run.resolution_note = notes or run.resolution_note
    run.resolution_action = (
        PaymentScheduleRun.ResolutionAction.PAID_OUTSIDE_VEXXO
        if paid_outside_vexxo
        else PaymentScheduleRun.ResolutionAction.MARK_PAID
    )
    run.status = (
        PaymentScheduleRun.Status.PAID_OUTSIDE_VEXXO
        if paid_outside_vexxo
        else PaymentScheduleRun.Status.PAID
    )
    run.save(
        update_fields=[
            "materialized_transaction",
            "paid_at",
            "resolved_at",
            "resolution_note",
            "resolution_action",
            "status",
            "updated_at",
        ]
    )
    publish_schedule_run_signal(
        owner_id=run.owner_id,
        schedule_run_id=run.pk,
        event="payment.schedule_run.paid_outside_vexxo" if paid_outside_vexxo else "payment.schedule_run.paid",
        extra=_run_payload(run),
    )
    if run.template.cadence == PaymentTemplate.Cadence.ONCE and run.template.is_active:
        run.template.is_active = False
        run.template.save(update_fields=["is_active", "updated_at"])
    return run


@transaction.atomic
def postpone_schedule_run(run: PaymentScheduleRun, *, new_due_on, actor=None, note: str = "") -> PaymentScheduleRun:
    if run.status in TERMINAL_RUN_STATUSES:
        return run
    run.postponed_until = new_due_on
    run.due_on = new_due_on
    scheduled_time = timezone.localtime(run.scheduled_for).timetz() if timezone.is_aware(run.scheduled_for) else run.scheduled_for.time()
    naive_dt = datetime.combine(new_due_on, scheduled_time.replace(tzinfo=None) if hasattr(scheduled_time, "tzinfo") else scheduled_time)
    if timezone.is_aware(run.scheduled_for):
        run.scheduled_for = timezone.make_aware(naive_dt, timezone.get_current_timezone())
    else:
        run.scheduled_for = naive_dt
    run.status = PaymentScheduleRun.Status.POSTPONED
    run.resolution_action = PaymentScheduleRun.ResolutionAction.POSTPONE
    run.resolution_note = note or run.resolution_note
    run.reminder_stage = 0
    run.save(
        update_fields=[
            "postponed_until",
            "due_on",
            "scheduled_for",
            "status",
            "resolution_action",
            "resolution_note",
            "reminder_stage",
            "updated_at",
        ]
    )
    publish_schedule_run_signal(
        owner_id=run.owner_id,
        schedule_run_id=run.pk,
        event="payment.schedule_run.postponed",
        extra=_run_payload(run),
    )
    return run


@transaction.atomic
def skip_schedule_run(run: PaymentScheduleRun, *, actor=None, note: str = "") -> PaymentScheduleRun:
    if run.status in TERMINAL_RUN_STATUSES:
        return run
    run.status = PaymentScheduleRun.Status.SKIPPED
    run.resolved_at = timezone.now()
    run.resolution_action = PaymentScheduleRun.ResolutionAction.SKIP
    run.resolution_note = note or run.resolution_note
    run.save(update_fields=["status", "resolved_at", "resolution_action", "resolution_note", "updated_at"])
    publish_schedule_run_signal(
        owner_id=run.owner_id,
        schedule_run_id=run.pk,
        event="payment.schedule_run.skipped",
        extra=_run_payload(run),
    )
    if run.template.cadence == PaymentTemplate.Cadence.ONCE and run.template.is_active:
        run.template.is_active = False
        run.template.save(update_fields=["is_active", "updated_at"])
    return run


@transaction.atomic
def cancel_schedule_run(run: PaymentScheduleRun, *, actor=None, note: str = "") -> PaymentScheduleRun:
    run = PaymentScheduleRun.objects.select_related("payment_intent", "template").get(pk=run.pk)
    if run.status in TERMINAL_RUN_STATUSES:
        return run
    _assert_manual_resolution_allowed(run, action_label="cancelar")
    run.status = PaymentScheduleRun.Status.CANCELED
    run.resolved_at = timezone.now()
    run.resolution_action = PaymentScheduleRun.ResolutionAction.CANCEL
    run.resolution_note = note or run.resolution_note
    run.save(update_fields=["status", "resolved_at", "resolution_action", "resolution_note", "updated_at"])
    publish_schedule_run_signal(
        owner_id=run.owner_id,
        schedule_run_id=run.pk,
        event="payment.schedule_run.canceled",
        extra=_run_payload(run),
    )
    if run.template.cadence == PaymentTemplate.Cadence.ONCE and run.template.is_active:
        run.template.is_active = False
        run.template.save(update_fields=["is_active", "updated_at"])
    return run


@transaction.atomic
def retry_failed_schedule_run(
    run: PaymentScheduleRun,
    *,
    actor=None,
    new_due_on=None,
    note: str = "",
) -> PaymentScheduleRun:
    run = PaymentScheduleRun.objects.select_related("template", "payment_intent").get(pk=run.pk)
    if run.status != PaymentScheduleRun.Status.FAILED:
        raise ValueError("Solo puedes reintentar ocurrencias en estado failed.")
    scheduled_time = timezone.localtime(run.scheduled_for).timetz() if timezone.is_aware(run.scheduled_for) else run.scheduled_for.time()
    retry_due_on = new_due_on or timezone.localdate()
    naive_dt = datetime.combine(retry_due_on, scheduled_time.replace(tzinfo=None) if hasattr(scheduled_time, "tzinfo") else scheduled_time)
    retry_scheduled_for = (
        timezone.make_aware(naive_dt, timezone.get_current_timezone())
        if timezone.is_aware(run.scheduled_for)
        else naive_dt
    )
    replacement = request_payment_schedule_run(
        template=run.template,
        scheduled_for=retry_scheduled_for,
        run_payload={
            **dict(run.run_payload or {}),
            "origin": "retry",
            "retry_of_schedule_run_id": str(run.pk),
        },
    )
    if replacement.pk == run.pk:
        raise ValueError("No fue posible crear una nueva ocurrencia de retry.")
    replacement.expected_amount = run.expected_amount or replacement.expected_amount
    replacement.expected_currency = run.expected_currency or replacement.expected_currency
    replacement.save(update_fields=["expected_amount", "expected_currency", "updated_at"])
    payload = dict(run.run_payload or {})
    payload["retried_by_schedule_run_id"] = str(replacement.pk)
    run.run_payload = payload
    run.resolution_note = note or run.resolution_note
    run.save(update_fields=["run_payload", "resolution_note", "updated_at"])
    publish_schedule_run_signal(
        owner_id=run.owner_id,
        schedule_run_id=replacement.pk,
        event="payment.schedule_run.retry_requested",
        extra=_run_payload(replacement),
    )
    return replacement


@transaction.atomic
def process_due_schedule_runs(*, as_of_date=None, limit: int = 200) -> dict:
    as_of_date = as_of_date or timezone.localdate()
    queryset = (
        PaymentScheduleRun.objects.select_for_update(skip_locked=True)
        .select_related("template", "owner")
        .filter(template__is_active=True)
        .exclude(status__in=list(TERMINAL_RUN_STATUSES))
        .order_by("due_on", "scheduled_for", "id")[: max(1, int(limit or 200))]
    )
    processed = 0
    reminders_sent = 0
    due_marked = 0
    overdue_marked = 0
    for run in queryset:
        previous_status = run.status
        _sync_run_status_from_dates(run, as_of_date=as_of_date)
        stage = _reminder_stage_for(run, as_of_date=as_of_date)
        if stage and stage > run.reminder_stage:
            _create_run_notification(run, stage=stage, as_of_date=as_of_date)
            reminders_sent += 1
        if run.status != previous_status:
            if run.status == PaymentScheduleRun.Status.DUE:
                due_marked += 1
            elif run.status == PaymentScheduleRun.Status.OVERDUE:
                overdue_marked += 1
        run.save(
            update_fields=[
                "status",
                "reminder_stage",
                "reminder_count",
                "last_reminded_at",
                "updated_at",
            ]
        )
        processed += 1
    return {
        "processed": processed,
        "reminders_sent": reminders_sent,
        "due_marked": due_marked,
        "overdue_marked": overdue_marked,
        "as_of_date": as_of_date.isoformat(),
    }


def get_schedule_run_operational_metrics(*, owner=None) -> dict:
    queryset = PaymentScheduleRun.objects.all()
    if owner is not None:
        queryset = queryset.filter(owner=owner)
    status_counts = {
        "due": queryset.filter(status=PaymentScheduleRun.Status.DUE).count(),
        "overdue": queryset.filter(status=PaymentScheduleRun.Status.OVERDUE).count(),
        "failed": queryset.filter(status=PaymentScheduleRun.Status.FAILED).count(),
        "processing": queryset.filter(status=PaymentScheduleRun.Status.PROCESSING).count(),
    }
    manual_closures = {
        "mark_paid": queryset.filter(resolution_action=PaymentScheduleRun.ResolutionAction.MARK_PAID).count(),
        "paid_outside_vexxo": queryset.filter(resolution_action=PaymentScheduleRun.ResolutionAction.PAID_OUTSIDE_VEXXO).count(),
        "skipped": queryset.filter(resolution_action=PaymentScheduleRun.ResolutionAction.SKIP).count(),
        "canceled": queryset.filter(resolution_action=PaymentScheduleRun.ResolutionAction.CANCEL).count(),
        "postponed": queryset.filter(resolution_action=PaymentScheduleRun.ResolutionAction.POSTPONE).count(),
    }
    templates_with_multiple_open_runs = (
        queryset.exclude(status__in=list(TERMINAL_RUN_STATUSES))
        .values("template_id")
        .annotate(open_runs=Count("id"))
        .filter(open_runs__gt=1)
        .count()
    )
    conflicts_manual_vs_intent = queryset.filter(
        payment_intent__isnull=False,
        materialized_transaction__isnull=False,
        resolution_action__in=[
            PaymentScheduleRun.ResolutionAction.MARK_PAID,
            PaymentScheduleRun.ResolutionAction.PAID_OUTSIDE_VEXXO,
        ],
    ).count()
    superseded_cancellations = queryset.filter(
        status=PaymentScheduleRun.Status.CANCELED,
        resolution_action=PaymentScheduleRun.ResolutionAction.CANCEL,
        resolution_note="Superseded by template schedule update.",
    ).count()
    reminder_count_total = int(queryset.aggregate(total=Sum("reminder_count")).get("total") or 0)
    return {
        "runs": status_counts,
        "manual_closures": manual_closures,
        "reminders_sent_total": reminder_count_total,
        "conflicts_manual_vs_intent": conflicts_manual_vs_intent,
        "templates_with_multiple_open_runs": templates_with_multiple_open_runs,
        "superseded_cancellations": superseded_cancellations,
    }


def sync_schedule_run_from_payment_intent_status(*, payment_intent) -> PaymentScheduleRun | None:
    run = (
        PaymentScheduleRun.objects.select_related("template")
        .filter(payment_intent_id=payment_intent.pk)
        .order_by("-id")
        .first()
    )
    if run is None:
        return None
    if payment_intent.status in {
        PaymentIntent.Status.SUCCEEDED,
        PaymentIntent.Status.SETTLED,
    }:
        resolved_paid_at = getattr(payment_intent, "updated_at", None)
        if resolved_paid_at is not None and hasattr(resolved_paid_at, "date"):
            resolved_paid_at = resolved_paid_at.date()
        run.status = PaymentScheduleRun.Status.PAID
        run.resolved_at = timezone.now()
        run.paid_at = resolved_paid_at or timezone.now().date()
        run.resolution_action = PaymentScheduleRun.ResolutionAction.PAY_WITH_VEXXO
        run.save(update_fields=["status", "resolved_at", "paid_at", "resolution_action", "updated_at"])
        publish_schedule_run_signal(
            owner_id=run.owner_id,
            schedule_run_id=run.pk,
            event="payment.schedule_run.paid",
            extra=_run_payload(run),
        )
    elif payment_intent.status in {
        PaymentIntent.Status.CANCELLED,
        PaymentIntent.Status.FAILED,
    }:
        run.status = PaymentScheduleRun.Status.FAILED if payment_intent.status == PaymentIntent.Status.FAILED else PaymentScheduleRun.Status.CANCELED
        run.failure_message = getattr(payment_intent, "failure_message", "") or run.failure_message
        run.resolved_at = timezone.now()
        if run.status == PaymentScheduleRun.Status.CANCELED:
            run.resolution_action = PaymentScheduleRun.ResolutionAction.CANCEL
        run.save(update_fields=["status", "failure_message", "resolved_at", "resolution_action", "updated_at"])
        publish_schedule_run_signal(
            owner_id=run.owner_id,
            schedule_run_id=run.pk,
            event="payment.schedule_run.failed" if run.status == PaymentScheduleRun.Status.FAILED else "payment.schedule_run.canceled",
            extra=_run_payload(run),
        )
    return run


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
        budget_scope="",
        shared_budget=None,
        budget_attribution_source="",
    )
    return template
