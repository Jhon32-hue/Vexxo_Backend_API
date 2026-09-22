from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.utils import timezone

from finance.debts.domain_events import DebtDomainEventTypes
from finance.debts.event_service import enqueue_debt_event
from finance.debts.models import Debt, DebtInstallment, DebtRestructuring
from finance.debts.utils import add_months, add_weeks, q


class DebtLifecycleError(ValueError):
    pass


SCHEDULE_FIELDS = {
    "principal",
    "start_date",
    "interest_rate",
    "interest_type",
    "compounding",
    "term_months",
    "total_installments",
    "frequency",
}


def _debt_payload(debt: Debt) -> dict:
    return {
        "debt_id": debt.pk,
        "owner_id": debt.owner_id,
        "status": debt.status,
        "currency": debt.currency,
        "total_installments": debt.total_installments,
    }


def _installment_due_date(debt: Debt, index: int) -> date:
    offset = index - 1
    if debt.frequency == "weekly":
        return add_weeks(debt.start_date, offset)
    if debt.frequency == "biweekly":
        return add_weeks(debt.start_date, offset * 2)
    if debt.frequency == "quarterly":
        return add_months(debt.start_date, offset * 3)
    if debt.frequency == "yearly":
        return add_months(debt.start_date, offset * 12)
    return add_months(debt.start_date, offset)


def _set_debt_status(debt: Debt, *, emit_event: bool = True) -> str:
    installments = list(debt.installments.only("status"))
    new_status = "active"
    if installments and all(item.status == "paid" for item in installments):
        new_status = "closed"
    elif any(item.status == "overdue" for item in installments):
        new_status = "overdue"

    previous = debt.status
    closed_at = debt.closed_at
    if new_status == "closed":
        closed_at = closed_at or timezone.now()
    elif previous == "closed":
        closed_at = None

    if previous != new_status or debt.closed_at != closed_at:
        debt.status = new_status
        debt.closed_at = closed_at
        debt.save(update_fields=["status", "closed_at", "updated_at"])
        if emit_event and previous != new_status:
            enqueue_debt_event(
                event_type=DebtDomainEventTypes.STATUS_CHANGED,
                aggregate_type="debt",
                aggregate_id=debt.pk,
                payload={**_debt_payload(debt), "previous_status": previous},
            )
    return new_status


@transaction.atomic
def create_debt(*, owner, **validated_data) -> Debt:
    validated_data = dict(validated_data)
    for protected in ("owner", "status", "closed_at", "created_at", "updated_at"):
        validated_data.pop(protected, None)
    principal = q(validated_data.get("principal"))
    if principal <= 0:
        raise DebtLifecycleError("El principal debe ser mayor que cero.")
    total_installments = validated_data.get("total_installments")
    if total_installments is not None and int(total_installments) <= 0:
        raise DebtLifecycleError("El numero de cuotas debe ser mayor que cero.")

    debt = Debt.objects.create(owner=owner, status="active", **validated_data)
    created = generate_installments_for_debt(debt, emit_event=False)
    enqueue_debt_event(
        event_type=DebtDomainEventTypes.DEBT_CREATED,
        aggregate_type="debt",
        aggregate_id=debt.pk,
        payload={**_debt_payload(debt), "generated_installments": created},
    )
    if created:
        enqueue_debt_event(
            event_type=DebtDomainEventTypes.INSTALLMENTS_GENERATED,
            aggregate_type="debt",
            aggregate_id=debt.pk,
            payload={**_debt_payload(debt), "generated_installments": created},
        )
    return debt


@transaction.atomic
def update_debt(*, debt: Debt, owner, changes: dict) -> Debt:
    debt = Debt.objects.select_for_update().get(pk=debt.pk, owner=owner)
    changes = dict(changes)
    for protected in ("owner", "status", "closed_at", "created_at", "updated_at"):
        changes.pop(protected, None)
    schedule_changed = any(
        field in changes and getattr(debt, field) != changes[field] for field in SCHEDULE_FIELDS
    )
    if schedule_changed and debt.installments.exists():
        protected = debt.installments.filter(paid_amount__gt=0).exists()
        linked = debt.installments.filter(payment_template__isnull=False).exists()
        if protected or linked:
            raise DebtLifecycleError(
                "No se puede recalcular el plan cuando existen pagos o pagos programados vinculados."
            )
        debt.installments.all().delete()

    changed_fields = []
    for field, value in changes.items():
        if getattr(debt, field) != value:
            setattr(debt, field, value)
            changed_fields.append(field)
    if changed_fields:
        debt.save(update_fields=[*changed_fields, "updated_at"])
    generated = generate_installments_for_debt(debt, emit_event=False) if schedule_changed else 0
    enqueue_debt_event(
        event_type=DebtDomainEventTypes.DEBT_UPDATED,
        aggregate_type="debt",
        aggregate_id=debt.pk,
        payload={
            **_debt_payload(debt),
            "changed_fields": sorted(changed_fields),
            "generated_installments": generated,
        },
    )
    return debt


@transaction.atomic
def delete_debt(*, debt: Debt, owner) -> None:
    debt = Debt.objects.select_for_update().get(pk=debt.pk, owner=owner)
    if debt.installments.filter(paid_amount__gt=0).exists() or debt.transactions.exists():
        raise DebtLifecycleError("Una deuda con pagos o transacciones no puede eliminarse.")
    payload = _debt_payload(debt)
    debt_id = debt.pk
    debt.delete()
    enqueue_debt_event(
        event_type=DebtDomainEventTypes.DEBT_DELETED,
        aggregate_type="debt",
        aggregate_id=debt_id,
        payload=payload,
    )


@transaction.atomic
def generate_installments_for_debt(debt: Debt, *, emit_event: bool = True) -> int:
    debt = Debt.objects.select_for_update().get(pk=debt.pk)
    count = int(debt.total_installments or 0)
    if count <= 0 or DebtInstallment.objects.filter(debt=debt).exists():
        return 0

    principal = q(debt.principal)
    rate = q(debt.interest_rate or 0)
    per_installment = (principal / q(count)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    remaining = principal
    installments = []
    for number in range(1, count + 1):
        interest = Decimal("0.00")
        if debt.interest_type != "none":
            interest = (remaining * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        principal_component = per_installment if number < count else remaining
        amount_due = (principal_component + interest).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        installments.append(
            DebtInstallment(
                owner=debt.owner,
                debt=debt,
                number=number,
                due_date=_installment_due_date(debt, number),
                amount_due=amount_due,
                principal_component=principal_component,
                interest_component=interest,
            )
        )
        remaining = (remaining - principal_component).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    DebtInstallment.objects.bulk_create(installments)
    if emit_event:
        enqueue_debt_event(
            event_type=DebtDomainEventTypes.INSTALLMENTS_GENERATED,
            aggregate_type="debt",
            aggregate_id=debt.pk,
            payload={**_debt_payload(debt), "generated_installments": len(installments)},
        )
    return len(installments)


@transaction.atomic
def create_debt_installment(*, owner, **validated_data) -> DebtInstallment:
    validated_data = dict(validated_data)
    for protected in (
        "owner",
        "status",
        "paid_amount",
        "paid_date",
        "paid_transaction",
        "created_at",
        "updated_at",
    ):
        validated_data.pop(protected, None)
    debt = validated_data["debt"]
    if debt.owner_id != owner.id:
        raise DebtLifecycleError("La deuda no pertenece al usuario autenticado.")
    if q(validated_data.get("amount_due")) <= 0:
        raise DebtLifecycleError("El valor de la cuota debe ser mayor que cero.")
    installment = DebtInstallment.objects.create(owner=owner, **validated_data)
    _set_debt_status(debt)
    enqueue_debt_event(
        event_type=DebtDomainEventTypes.INSTALLMENT_UPDATED,
        aggregate_type="debt_installment",
        aggregate_id=installment.pk,
        payload={
            "debt_id": debt.pk,
            "installment_id": installment.pk,
            "owner_id": owner.id,
            "operation": "created",
        },
    )
    return installment


@transaction.atomic
def update_debt_installment(*, installment: DebtInstallment, owner, changes: dict) -> DebtInstallment:
    installment = DebtInstallment.objects.select_for_update().get(pk=installment.pk, owner=owner)
    changes = dict(changes)
    for protected in (
        "owner",
        "status",
        "paid_amount",
        "paid_date",
        "paid_transaction",
        "created_at",
        "updated_at",
    ):
        changes.pop(protected, None)
    requested_debt = changes.pop("debt", installment.debt)
    if requested_debt.pk != installment.debt_id:
        raise DebtLifecycleError("Una cuota existente no puede trasladarse a otra deuda.")
    if installment.paid_amount > 0:
        mutable = {"payment_template"}
        if any(field not in mutable for field in changes):
            raise DebtLifecycleError("Una cuota con pagos solo permite actualizar su pago programado.")
    changed_fields = []
    for field, value in changes.items():
        if getattr(installment, field) != value:
            setattr(installment, field, value)
            changed_fields.append(field)
    if changed_fields:
        installment.save(update_fields=[*changed_fields, "updated_at"])
    _set_debt_status(installment.debt)
    enqueue_debt_event(
        event_type=DebtDomainEventTypes.INSTALLMENT_UPDATED,
        aggregate_type="debt_installment",
        aggregate_id=installment.pk,
        payload={
            "debt_id": installment.debt_id,
            "installment_id": installment.pk,
            "owner_id": owner.id,
            "operation": "updated",
            "changed_fields": sorted(changed_fields),
        },
    )
    return installment


@transaction.atomic
def delete_debt_installment(*, installment: DebtInstallment, owner) -> None:
    installment = DebtInstallment.objects.select_for_update().get(pk=installment.pk, owner=owner)
    if installment.paid_amount > 0 or installment.paid_transaction_id:
        raise DebtLifecycleError("Una cuota con pagos no puede eliminarse.")
    debt = installment.debt
    installment_id = installment.pk
    installment.delete()
    _set_debt_status(debt)
    enqueue_debt_event(
        event_type=DebtDomainEventTypes.INSTALLMENT_UPDATED,
        aggregate_type="debt_installment",
        aggregate_id=installment_id,
        payload={
            "debt_id": debt.pk,
            "installment_id": installment_id,
            "owner_id": owner.id,
            "operation": "deleted",
        },
    )


@transaction.atomic
def apply_payment_to_debt(
    debt: Debt,
    amount: Decimal,
    pay_date: date,
    installment: Optional[DebtInstallment] = None,
    *,
    transaction_obj=None,
    emit_event: bool = True,
) -> Decimal:
    debt = Debt.objects.select_for_update().get(pk=debt.pk)
    requested = q(amount)
    if requested <= 0:
        raise DebtLifecycleError("El pago debe ser mayor que cero.")
    if installment is not None and installment.debt_id != debt.pk:
        raise DebtLifecycleError("La cuota no pertenece a la deuda indicada.")

    queryset = DebtInstallment.objects.select_for_update().filter(debt=debt).order_by("number")
    if installment is not None:
        queryset = queryset.filter(pk=installment.pk)

    remaining = requested
    allocations = []
    for item in queryset:
        if remaining <= 0:
            break
        outstanding = q(item.amount_due - item.paid_amount)
        if outstanding <= 0:
            continue
        applied = min(outstanding, remaining)
        item.paid_amount = (item.paid_amount + applied).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        item.paid_date = pay_date
        item.status = "paid" if item.paid_amount >= item.amount_due else "partial"
        if transaction_obj is not None:
            item.paid_transaction = transaction_obj
        item.save(
            update_fields=["paid_amount", "paid_date", "status", "paid_transaction", "updated_at"]
        )
        allocations.append({"installment_id": item.pk, "amount": str(applied)})
        remaining -= applied

    applied_total = requested - remaining
    _set_debt_status(debt, emit_event=emit_event)
    if emit_event and applied_total > 0:
        transaction_id = getattr(transaction_obj, "pk", None)
        enqueue_debt_event(
            event_type=DebtDomainEventTypes.PAYMENT_APPLIED,
            aggregate_type="debt",
            aggregate_id=debt.pk,
            payload={
                **_debt_payload(debt),
                "requested_amount": str(requested),
                "applied_amount": str(applied_total),
                "transaction_id": transaction_id,
                "allocations": allocations,
            },
            correlation_id=str(transaction_id or ""),
        )
    return applied_total


@transaction.atomic
def refresh_overdue_installments(*, as_of: date | None = None, owner=None) -> int:
    as_of = as_of or timezone.localdate()
    queryset = DebtInstallment.objects.select_for_update().filter(status="due", due_date__lt=as_of)
    if owner is not None:
        queryset = queryset.filter(owner=owner)
    installments = list(queryset.select_related("debt"))
    debt_ids = set()
    for installment in installments:
        installment.status = "overdue"
        installment.save(update_fields=["status", "updated_at"])
        debt_ids.add(installment.debt_id)
    for debt in Debt.objects.select_for_update().filter(pk__in=debt_ids):
        _set_debt_status(debt)
    if installments:
        enqueue_debt_event(
            event_type=DebtDomainEventTypes.OVERDUE_REFRESHED,
            aggregate_type="debt_batch",
            aggregate_id=as_of.isoformat(),
            payload={
                "as_of": as_of.isoformat(),
                "updated_installments": len(installments),
                "debt_ids": sorted(debt_ids),
            },
        )
    return len(installments)


@transaction.atomic
def reconcile_debt_payments(debt: Debt) -> None:
    debt = Debt.objects.select_for_update().get(pk=debt.pk)
    installments = list(
        DebtInstallment.objects.select_for_update().filter(debt=debt).order_by("number")
    )
    for installment in installments:
        installment.paid_amount = Decimal("0.00")
        installment.paid_date = None
        installment.paid_transaction = None
        installment.status = "due"
        installment.save(
            update_fields=[
                "paid_amount",
                "paid_date",
                "paid_transaction",
                "status",
                "updated_at",
            ]
        )

    from finance.transactions.Models.transacciones import Transaction
    from finance.transactions.transaction_state_service import is_transaction_countable_for_ledger

    applied_transaction_ids = []
    transactions = (
        Transaction.objects.filter(debt=debt, type=Transaction.Type.EXPENSE)
        .select_related("installment")
        .order_by("date", "id")
    )
    for transaction_obj in transactions:
        if not is_transaction_countable_for_ledger(transaction_obj):
            continue
        apply_payment_to_debt(
            debt=debt,
            amount=Decimal(transaction_obj.amount),
            pay_date=transaction_obj.date,
            installment=transaction_obj.installment if transaction_obj.installment_id else None,
            transaction_obj=transaction_obj,
            emit_event=False,
        )
        applied_transaction_ids.append(transaction_obj.pk)
    _set_debt_status(debt, emit_event=False)
    enqueue_debt_event(
        event_type=DebtDomainEventTypes.PAYMENT_APPLIED,
        aggregate_type="debt",
        aggregate_id=debt.pk,
        payload={
            **_debt_payload(debt),
            "reconciled": True,
            "transaction_ids": applied_transaction_ids,
        },
    )


def _terms_snapshot(debt: Debt) -> dict:
    return {
        "principal": str(debt.principal),
        "currency": debt.currency,
        "start_date": debt.start_date.isoformat(),
        "interest_rate": str(debt.interest_rate),
        "interest_type": debt.interest_type,
        "compounding": debt.compounding,
        "term_months": debt.term_months,
        "total_installments": debt.total_installments,
        "frequency": debt.frequency,
    }


@transaction.atomic
def restructure_debt(
    *,
    debt: Debt,
    owner,
    effective_date: date,
    reason: str,
    idempotency_key: str,
    new_terms: dict,
    installments: list[dict],
) -> tuple[DebtRestructuring, bool]:
    debt = Debt.objects.select_for_update().get(pk=debt.pk, owner=owner)
    key = str(idempotency_key or "").strip()
    if not 8 <= len(key) <= 160:
        raise DebtLifecycleError("Idempotency-Key debe tener entre 8 y 160 caracteres.")
    existing = DebtRestructuring.objects.filter(owner=owner, idempotency_key=key).first()
    if existing:
        if existing.debt_id != debt.pk:
            raise DebtLifecycleError("Idempotency-Key ya fue usado para otra deuda.")
        return existing, False
    reason = str(reason or "").strip()
    if len(reason) < 10:
        raise DebtLifecycleError("La reestructuracion requiere un motivo de al menos 10 caracteres.")
    if not installments:
        raise DebtLifecycleError("La reestructuracion requiere un nuevo calendario de cuotas.")

    locked_installments = list(DebtInstallment.objects.select_for_update().filter(debt=debt).order_by("number"))
    if any(item.status == "partial" or (item.paid_amount > 0 and item.status != "paid") for item in locked_installments):
        raise DebtLifecycleError("Resuelve o reconcilia las cuotas parciales antes de reestructurar.")
    preserved = [item for item in locked_installments if item.paid_amount > 0 or item.status == "paid"]
    replaceable = [item for item in locked_installments if item not in preserved]
    replaced_ids = [item.pk for item in replaceable]
    next_number = max((item.number for item in preserved), default=0) + 1

    normalized_schedule = []
    for index, raw in enumerate(installments, start=next_number):
        due_date = raw.get("due_date")
        if not isinstance(due_date, date) or due_date < effective_date:
            raise DebtLifecycleError("Cada nueva cuota debe vencer en o despues de effective_date.")
        amount_due = q(raw.get("amount_due"))
        principal_component = q(raw.get("principal_component", amount_due))
        interest_component = q(raw.get("interest_component", 0))
        if amount_due <= 0 or principal_component < 0 or interest_component < 0:
            raise DebtLifecycleError("Los componentes del nuevo calendario no son validos.")
        if abs(amount_due - principal_component - interest_component) > Decimal("0.01"):
            raise DebtLifecycleError("amount_due debe coincidir con principal_component + interest_component.")
        normalized_schedule.append(
            {
                "number": index,
                "due_date": due_date,
                "amount_due": amount_due,
                "principal_component": principal_component,
                "interest_component": interest_component,
            }
        )

    previous_terms = _terms_snapshot(debt)
    terms = dict(new_terms or {})
    if terms.get("currency") and str(terms["currency"]).upper() != debt.currency:
        raise DebtLifecycleError("Una reestructuracion no puede cambiar la moneda de la deuda.")
    allowed_fields = {
        "principal",
        "interest_rate",
        "interest_type",
        "compounding",
        "term_months",
        "frequency",
    }
    changed_fields = []
    for field in allowed_fields:
        if field not in terms:
            continue
        value = terms[field]
        if field in {"principal", "interest_rate"}:
            value = q(value)
        if getattr(debt, field) != value:
            setattr(debt, field, value)
            changed_fields.append(field)
    debt.start_date = effective_date
    debt.total_installments = len(preserved) + len(normalized_schedule)
    debt.status = "active"
    debt.closed_at = None
    changed_fields.extend(["start_date", "total_installments", "status", "closed_at"])

    DebtInstallment.objects.filter(pk__in=replaced_ids).delete()
    created = DebtInstallment.objects.bulk_create(
        [DebtInstallment(owner=owner, debt=debt, **row) for row in normalized_schedule]
    )
    debt.save(update_fields=[*sorted(set(changed_fields)), "updated_at"])
    resulting_terms = _terms_snapshot(debt)
    restructuring = DebtRestructuring.objects.create(
        owner=owner,
        debt=debt,
        idempotency_key=key,
        effective_date=effective_date,
        reason=reason[:500],
        previous_terms=previous_terms,
        new_terms=resulting_terms,
        replaced_installment_ids=replaced_ids,
        created_installment_ids=[item.pk for item in created],
    )
    enqueue_debt_event(
        event_type=DebtDomainEventTypes.RESTRUCTURED,
        aggregate_type="debt",
        aggregate_id=debt.pk,
        payload={
            **_debt_payload(debt),
            "restructuring_id": restructuring.pk,
            "effective_date": effective_date.isoformat(),
            "previous_terms": previous_terms,
            "new_terms": resulting_terms,
            "replaced_installment_ids": replaced_ids,
            "created_installment_ids": restructuring.created_installment_ids,
        },
        idempotency_key=f"debt-restructuring:{owner.pk}:{key}",
    )
    return restructuring, True
