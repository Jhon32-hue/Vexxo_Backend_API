from __future__ import annotations

import hashlib
import json
from decimal import ROUND_DOWN, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from finance.transactions.Models import Transaction, TransactionParticipant
from finance.transactions.transaction_write_service import create_manual_transaction
from notifications.deliveries.models import NotificationChannel
from notifications.deliveries.services import create_notification_delivery
from social.shared_expenses.event_service import enqueue_shared_expense_event
from social.shared_expenses.models import SharedExpense, SharedExpenseSettlement, SharedExpenseShare

CENT = Decimal("0.01")
HUNDRED = Decimal("100.00")


class SharedExpenseConflict(Exception):
    def __init__(self, message: str, *, expense: SharedExpense | None = None):
        self.expense = expense
        super().__init__(message)


def canonical_request_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT)


def _participant_key(spec: dict, index: int) -> str:
    return ":".join(
        [
            "0" if spec.get("is_payer") else "1",
            str(spec.get("participant_user_id") or ""),
            str(spec.get("contact_id") or ""),
            str(spec.get("email") or "").strip().lower(),
            str(spec.get("display_name") or "").strip().lower(),
            f"{index:04d}",
        ]
    )


def calculate_shares(*, total: Decimal, method: str, specs: list[dict]) -> list[dict]:
    total = _money(total)
    if total <= 0:
        raise ValidationError({"total_amount": "El total debe ser mayor a cero."})
    if len(specs) < 2:
        raise ValidationError({"shares": "Un gasto compartido requiere al menos dos partes."})
    if sum(bool(item.get("is_payer")) for item in specs) != 1:
        raise ValidationError({"shares": "Debe existir exactamente una parte para el pagador."})

    ordered = sorted(enumerate(specs), key=lambda item: _participant_key(item[1], item[0]))
    amounts: dict[int, Decimal] = {}
    if method == SharedExpense.SplitMethod.EXACT_AMOUNT:
        for index, spec in enumerate(specs):
            amount = _money(spec.get("amount") or 0)
            if amount <= 0:
                raise ValidationError({"shares": "Cada monto exacto debe ser mayor a cero."})
            amounts[index] = amount
        if sum(amounts.values(), Decimal("0.00")) != total:
            raise ValidationError({"shares": "La suma de montos debe coincidir exactamente con el total."})
    else:
        if method == SharedExpense.SplitMethod.EQUAL:
            factors = {index: Decimal("1") for index, _spec in ordered}
        elif method == SharedExpense.SplitMethod.PERCENTAGE:
            factors = {index: Decimal(str(spec.get("percentage") or 0)) for index, spec in enumerate(specs)}
            if sum(factors.values(), Decimal("0")) != HUNDRED:
                raise ValidationError({"shares": "Los porcentajes deben sumar exactamente 100."})
        elif method == SharedExpense.SplitMethod.WEIGHTED:
            factors = {index: Decimal(str(spec.get("weight") or 0)) for index, spec in enumerate(specs)}
        else:
            raise ValidationError({"split_method": "Metodo de division no soportado."})
        if any(value <= 0 for value in factors.values()):
            raise ValidationError({"shares": "Todos los factores deben ser mayores a cero."})
        factor_total = sum(factors.values(), Decimal("0"))
        for index, _spec in ordered:
            amounts[index] = (total * factors[index] / factor_total).quantize(CENT, rounding=ROUND_DOWN)
        residue_cents = int(((total - sum(amounts.values(), Decimal("0.00"))) / CENT).to_integral_value())
        for index, _spec in ordered[:residue_cents]:
            amounts[index] += CENT

    calculated = []
    for index, spec in enumerate(specs):
        calculated.append(
            {
                **spec,
                "expected_amount": amounts[index],
                "percentage": Decimal(str(spec["percentage"])) if spec.get("percentage") is not None else None,
                "weight": Decimal(str(spec["weight"])) if spec.get("weight") is not None else None,
            }
        )
    return calculated


def _assert_team_access(team, actor) -> None:
    if team is None:
        return
    if team.owner_id != actor.pk and not team.memberships.filter(user=actor, is_active=True).exists():
        raise PermissionDenied("No perteneces al equipo seleccionado.")


def _validate_share_identity(*, owner, spec: dict) -> None:
    contact = spec.get("contact")
    participant_user = spec.get("participant_user")
    if contact is not None and contact.owner_id != owner.pk:
        raise ValidationError({"shares": "Uno de los contactos no pertenece al pagador."})
    if spec.get("is_payer"):
        if participant_user is not None and participant_user.pk != owner.pk:
            raise ValidationError({"shares": "El pagador no coincide con el propietario."})
        spec["participant_user"] = owner
    elif participant_user is None and contact is not None and contact.linked_user_id:
        spec["participant_user"] = contact.linked_user
    if not str(spec.get("display_name") or "").strip():
        if spec.get("participant_user") is not None:
            spec["display_name"] = spec["participant_user"].display_name
        elif contact is not None:
            spec["display_name"] = contact.effective_name()
        else:
            raise ValidationError({"shares": "Cada parte debe tener un nombre visible."})
    spec["email"] = str(spec.get("email") or getattr(spec.get("participant_user"), "email", "") or "").strip().lower()


def _create_share_records(*, expense: SharedExpense, calculated: list[dict]) -> list[SharedExpenseShare]:
    records = []
    for spec in calculated:
        share = SharedExpenseShare(
            shared_expense=expense,
            participant_user=spec.get("participant_user"),
            contact=spec.get("contact"),
            is_payer=bool(spec.get("is_payer")),
            display_name=str(spec.get("display_name") or "")[:120],
            email=spec.get("email") or "",
            expected_amount=spec["expected_amount"],
            percentage=spec.get("percentage"),
            weight=spec.get("weight"),
            status=SharedExpenseShare.Status.ACCEPTED if spec.get("is_payer") else SharedExpenseShare.Status.PENDING,
            accepted_at=timezone.now() if spec.get("is_payer") else None,
        )
        share.full_clean()
        share.save()
        records.append(share)
        if share.participant_user_id and not share.is_payer:
            create_notification_delivery(
                owner=share.participant_user,
                title="Te invitaron a dividir un gasto",
                message=f"{expense.owner.display_name} te asigno {share.expected_amount} {expense.currency}.",
                event_type="shared_expenses.share.invited.v1",
                source="social.shared_expenses",
                payload={"shared_expense_id": str(expense.public_id), "share_id": str(share.public_id)},
                channel=NotificationChannel.IN_APP,
                dedupe_key=f"shared-expense-share:{share.public_id}:invited",
            )
    return records


@transaction.atomic
def create_shared_expense(
    *,
    actor,
    split_method: str,
    share_specs: list[dict],
    idempotency_key: str,
    request_hash: str,
    request_id: str = "",
    team=None,
    source_transaction: Transaction | None = None,
    transaction_validated_data: dict | None = None,
    tags_data=None,
) -> tuple[SharedExpense, bool]:
    idempotency_key = str(idempotency_key or "").strip()
    if not idempotency_key:
        raise ValidationError({"idempotency_key": "Idempotency-Key es requerido."})
    existing = SharedExpense.objects.select_for_update().filter(
        owner=actor, idempotency_key=idempotency_key
    ).first()
    if existing:
        if existing.request_hash != request_hash:
            raise SharedExpenseConflict("Idempotency-Key ya fue usada con otro payload.", expense=existing)
        return existing, False

    _assert_team_access(team, actor)
    if source_transaction is None:
        if transaction_validated_data is None:
            raise ValidationError({"transaction": "Debes indicar o crear la transaccion origen."})
        validated = dict(transaction_validated_data)
        budget_context = validated.pop("budget_context_shared_budget", None)
        source_transaction = create_manual_transaction(
            validated_data=validated,
            actor=actor,
            tags_data=tags_data,
            budget_context_shared_budget=budget_context,
            event_source="social.shared_expenses.create",
        )
    else:
        source_transaction = Transaction.objects.select_for_update().select_related("account").get(pk=source_transaction.pk)
    if source_transaction.owner_id != actor.pk:
        raise PermissionDenied("La transaccion origen no pertenece al pagador.")
    if source_transaction.type != Transaction.Type.EXPENSE:
        raise ValidationError({"transaction": "Solo los gastos se pueden dividir."})
    if hasattr(source_transaction, "shared_expense"):
        raise SharedExpenseConflict("La transaccion ya tiene un gasto compartido.")

    normalized_specs = []
    for original in share_specs:
        spec = dict(original)
        _validate_share_identity(owner=actor, spec=spec)
        spec["participant_user_id"] = getattr(spec.get("participant_user"), "pk", None)
        spec["contact_id"] = getattr(spec.get("contact"), "pk", None)
        normalized_specs.append(spec)
    calculated = calculate_shares(total=source_transaction.amount, method=split_method, specs=normalized_specs)
    currency = str(getattr(source_transaction.account, "currency", "") or actor.preferred_currency or "COP").upper()[:3]
    expense = SharedExpense(
        owner=actor,
        transaction=source_transaction,
        team=team,
        split_method=split_method,
        total_amount=source_transaction.amount,
        currency=currency,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    expense.full_clean()
    expense.save()
    _create_share_records(expense=expense, calculated=calculated)
    enqueue_shared_expense_event(
        expense=expense,
        event_type="shared_expenses.created.v1",
        action="created",
        actor_id=actor.pk,
        request_id=request_id,
        extra={"share_count": len(calculated), "split_method": split_method},
    )
    return expense, True


def _assert_version(expense: SharedExpense, base_version: int | None) -> None:
    if base_version is not None and expense.version != base_version:
        raise SharedExpenseConflict("El gasto compartido cambio en otro dispositivo.", expense=expense)


def _actor_can_accept(share: SharedExpenseShare, actor) -> bool:
    return bool(
        share.participant_user_id == actor.pk
        or (share.email and share.email.lower() == str(actor.email or "").strip().lower())
    )


def _recompute_expense_status(expense: SharedExpense) -> None:
    if expense.status in {SharedExpense.Status.CANCELED, SharedExpense.Status.DISPUTED}:
        return
    shares = list(expense.shares.filter(is_payer=False))
    if any(share.status == SharedExpenseShare.Status.DISPUTED for share in shares):
        expense.status = SharedExpense.Status.DISPUTED
    elif shares and all(share.status == SharedExpenseShare.Status.SETTLED for share in shares):
        expense.status = SharedExpense.Status.SETTLED
    elif any(share.paid_amount > 0 for share in shares):
        expense.status = SharedExpense.Status.PARTIALLY_SETTLED
    elif any(share.status == SharedExpenseShare.Status.PENDING for share in shares):
        expense.status = SharedExpense.Status.AWAITING_ACCEPTANCE
    else:
        expense.status = SharedExpense.Status.ACTIVE


@transaction.atomic
def accept_share(*, share: SharedExpenseShare, actor, base_version: int | None, request_id: str = "") -> SharedExpense:
    share = SharedExpenseShare.objects.select_for_update().get(pk=share.pk)
    expense = SharedExpense.objects.select_for_update().get(pk=share.shared_expense_id)
    if not _actor_can_accept(share, actor):
        raise PermissionDenied("Esta invitacion no pertenece al usuario autenticado.")
    if share.status in {
        SharedExpenseShare.Status.ACCEPTED,
        SharedExpenseShare.Status.PARTIALLY_SETTLED,
        SharedExpenseShare.Status.SETTLED,
    }:
        return expense
    _assert_version(expense, base_version)
    if share.status != SharedExpenseShare.Status.PENDING:
        raise SharedExpenseConflict("La parte ya no puede aceptarse.", expense=expense)
    participant = TransactionParticipant(
        owner=expense.owner,
        transaction=expense.transaction,
        contact=share.contact,
        linked_user=actor,
        display_name=share.display_name,
        email=share.email,
        direction=TransactionParticipant.Direction.USER_IS_CREDITOR,
        role=TransactionParticipant.Role.FRIEND,
        status=TransactionParticipant.Status.ACTIVE,
        invite_status=TransactionParticipant.InviteStatus.JOINED,
        share_amount=share.expected_amount,
    )
    participant.full_clean()
    participant.save()
    share.participant_user = actor
    share.transaction_participant = participant
    share.status = SharedExpenseShare.Status.ACCEPTED
    share.accepted_at = timezone.now()
    share.save(update_fields=["participant_user", "transaction_participant", "status", "accepted_at", "updated_at"])
    _recompute_expense_status(expense)
    expense.version += 1
    expense.save(update_fields=["status", "version", "updated_at"])
    enqueue_shared_expense_event(
        expense=expense,
        event_type="shared_expenses.share.accepted.v1",
        action=f"share-{share.public_id}-accepted",
        actor_id=actor.pk,
        request_id=request_id,
        extra={"share_id": str(share.public_id)},
    )
    return expense


@transaction.atomic
def dispute_share(*, share: SharedExpenseShare, actor, base_version: int | None, request_id: str = "") -> SharedExpense:
    share = SharedExpenseShare.objects.select_for_update().select_related("shared_expense").get(pk=share.pk)
    expense = SharedExpense.objects.select_for_update().get(pk=share.shared_expense_id)
    _assert_version(expense, base_version)
    if actor.pk != expense.owner_id and not _actor_can_accept(share, actor):
        raise PermissionDenied("No puedes disputar esta parte.")
    share.status = SharedExpenseShare.Status.DISPUTED
    share.disputed_at = timezone.now()
    share.save(update_fields=["status", "disputed_at", "updated_at"])
    expense.status = SharedExpense.Status.DISPUTED
    expense.version += 1
    expense.save(update_fields=["status", "version", "updated_at"])
    enqueue_shared_expense_event(
        expense=expense,
        event_type="shared_expenses.disputed.v1",
        action=f"share-{share.public_id}-disputed",
        actor_id=actor.pk,
        request_id=request_id,
        extra={"share_id": str(share.public_id)},
    )
    return expense


@transaction.atomic
def cancel_shared_expense(*, expense: SharedExpense, actor, base_version: int | None, request_id: str = "") -> SharedExpense:
    expense = SharedExpense.objects.select_for_update().get(pk=expense.pk)
    _assert_version(expense, base_version)
    if expense.owner_id != actor.pk:
        raise PermissionDenied("Solo el pagador puede cancelar el gasto compartido.")
    if expense.settlements.filter(status=SharedExpenseSettlement.Status.CONFIRMED).exists():
        raise SharedExpenseConflict("No se puede cancelar un gasto con liquidaciones confirmadas.", expense=expense)
    if expense.status == SharedExpense.Status.CANCELED:
        return expense
    expense.shares.exclude(status=SharedExpenseShare.Status.SETTLED).update(status=SharedExpenseShare.Status.CANCELED)
    TransactionParticipant.objects.filter(shared_expense_share__shared_expense=expense).update(
        status=TransactionParticipant.Status.CANCELED
    )
    expense.status = SharedExpense.Status.CANCELED
    expense.version += 1
    expense.save(update_fields=["status", "version", "updated_at"])
    enqueue_shared_expense_event(
        expense=expense,
        event_type="shared_expenses.canceled.v1",
        action="canceled",
        actor_id=actor.pk,
        request_id=request_id,
    )
    return expense


@transaction.atomic
def revise_shared_expense(
    *,
    expense: SharedExpense,
    actor,
    split_method: str,
    share_specs: list[dict],
    base_version: int,
    request_id: str = "",
) -> SharedExpense:
    expense = SharedExpense.objects.select_for_update().select_related("transaction").get(pk=expense.pk)
    _assert_version(expense, base_version)
    if expense.owner_id != actor.pk:
        raise PermissionDenied("Solo el pagador puede corregir la division.")
    if expense.settlements.filter(status=SharedExpenseSettlement.Status.CONFIRMED).exists():
        raise SharedExpenseConflict("No se puede corregir una division con liquidaciones.", expense=expense)
    if expense.shares.filter(is_payer=False).exclude(status=SharedExpenseShare.Status.PENDING).exists():
        raise SharedExpenseConflict("No se puede corregir despues de aceptar o disputar una parte.", expense=expense)

    normalized_specs = []
    for original in share_specs:
        spec = dict(original)
        _validate_share_identity(owner=actor, spec=spec)
        spec["participant_user_id"] = getattr(spec.get("participant_user"), "pk", None)
        spec["contact_id"] = getattr(spec.get("contact"), "pk", None)
        normalized_specs.append(spec)
    calculated = calculate_shares(total=expense.total_amount, method=split_method, specs=normalized_specs)
    expense.shares.all().delete()
    expense.split_method = split_method
    expense.status = SharedExpense.Status.AWAITING_ACCEPTANCE
    expense.version += 1
    expense.save(update_fields=["split_method", "status", "version", "updated_at"])
    _create_share_records(expense=expense, calculated=calculated)
    enqueue_shared_expense_event(
        expense=expense,
        event_type="shared_expenses.revised.v1",
        action="revised",
        actor_id=actor.pk,
        request_id=request_id,
        extra={"share_count": len(calculated), "split_method": split_method},
    )
    return expense


@transaction.atomic
def settle_share(
    *,
    share: SharedExpenseShare,
    actor,
    settlement_transaction: Transaction,
    amount: Decimal,
    idempotency_key: str,
    request_hash: str,
    base_version: int | None,
    request_id: str = "",
) -> tuple[SharedExpenseSettlement, bool]:
    idempotency_key = str(idempotency_key or "").strip()
    if not idempotency_key:
        raise ValidationError({"idempotency_key": "Idempotency-Key es requerido."})
    existing = SharedExpenseSettlement.objects.select_for_update().filter(
        recorded_by=actor, idempotency_key=idempotency_key
    ).first()
    if existing:
        if existing.request_hash != request_hash:
            raise SharedExpenseConflict("Idempotency-Key ya fue usada con otra liquidacion.")
        return existing, False
    share = SharedExpenseShare.objects.select_for_update().get(pk=share.pk)
    expense = SharedExpense.objects.select_for_update().get(pk=share.shared_expense_id)
    _assert_version(expense, base_version)
    if actor.pk != expense.owner_id and not _actor_can_accept(share, actor):
        raise PermissionDenied("No puedes liquidar esta parte.")
    if share.is_payer or share.status not in {
        SharedExpenseShare.Status.ACCEPTED,
        SharedExpenseShare.Status.PARTIALLY_SETTLED,
    }:
        raise SharedExpenseConflict("La parte debe estar aceptada para liquidarse.", expense=expense)
    settlement_transaction = Transaction.objects.select_for_update().get(pk=settlement_transaction.pk)
    if settlement_transaction.owner_id != actor.pk:
        raise PermissionDenied("La transaccion de liquidacion debe pertenecer a quien la registra.")
    amount = _money(amount)
    if amount <= 0 or amount > share.pending_amount:
        raise ValidationError({"amount": "El monto debe ser positivo y no superar el saldo pendiente."})
    settlement = SharedExpenseSettlement(
        shared_expense=expense,
        share=share,
        transaction=settlement_transaction,
        recorded_by=actor,
        amount=amount,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    settlement.full_clean()
    settlement.save()
    share.paid_amount = _money(share.paid_amount + amount)
    share.status = (
        SharedExpenseShare.Status.SETTLED
        if share.paid_amount == share.expected_amount
        else SharedExpenseShare.Status.PARTIALLY_SETTLED
    )
    share.save(update_fields=["paid_amount", "status", "updated_at"])
    if share.transaction_participant_id:
        participant = share.transaction_participant
        participant.paid_amount = share.paid_amount
        participant.normalize_state()
        participant.save(update_fields=["paid_amount", "status", "updated_at"])
    _recompute_expense_status(expense)
    expense.version += 1
    expense.save(update_fields=["status", "version", "updated_at"])
    enqueue_shared_expense_event(
        expense=expense,
        event_type="shared_expenses.settlement.recorded.v1",
        action=f"settlement-{settlement.public_id}",
        actor_id=actor.pk,
        request_id=request_id,
        extra={"share_id": str(share.public_id), "settlement_id": str(settlement.public_id), "amount": str(amount)},
    )
    return settlement, True
