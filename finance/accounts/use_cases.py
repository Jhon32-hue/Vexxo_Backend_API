# accounts/use_cases.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from finance.accounts.services.event_service import enqueue_domain_event, publish_after_commit
from finance.accounts.services.realtime_services import ping_account_changed
from finance.transactions.constants import POSTED_STATUSES, CREDIT_TYPES, DEBIT_TYPES

ZERO = Decimal("0.00")
PREC = Decimal("0.000001")  # tu modelo ya usa 6 decimales, consistente


@dataclass(frozen=True)
class TransactionBalanceState:
    tx_id: int | None
    account_id: int | None
    tx_type: str | None
    amount: Decimal | None
    status: str | None
    confirmed: bool | None
    affects_balance: bool | None


def _decimal(value) -> Decimal:
    if value is None:
        return ZERO
    try:
        return Decimal(str(value)).quantize(PREC)
    except (InvalidOperation, ValueError, TypeError):
        return ZERO


def _signed_effect(state: TransactionBalanceState | None) -> Decimal:
    """
    Efecto contable de una transacción sobre una cuenta.
    """
    if state is None or not state.account_id:
        return ZERO
    if not state.confirmed:
        return ZERO
    if not state.affects_balance:
        return ZERO
    if state.status not in POSTED_STATUSES:
        return ZERO

    amount = _decimal(state.amount)
    if state.tx_type in CREDIT_TYPES:
        return amount
    if state.tx_type in DEBIT_TYPES:
        return -amount
    return ZERO


def build_state_from_transaction(tx, *, prefix: str = "") -> TransactionBalanceState:
    p = f"{prefix}_" if prefix and not prefix.endswith("_") else prefix
    return TransactionBalanceState(
        tx_id=getattr(tx, f"{p}pk", None),
        account_id=getattr(tx, f"{p}account_id", None),
        tx_type=getattr(tx, f"{p}type", None),
        amount=getattr(tx, f"{p}amount", None),
        status=getattr(tx, f"{p}status", None),
        confirmed=getattr(tx, f"{p}confirmed", None),
        affects_balance=getattr(tx, f"{p}affects_balance", None),
    )


def calculate_account_balance_deltas(
    *,
    old_state: TransactionBalanceState | None,
    new_state: TransactionBalanceState | None,
) -> dict[int, Decimal]:
    """
    Delta por cuenta sin recalc completo:
    - revertir old_state
    - aplicar new_state
    """
    deltas: dict[int, Decimal] = {}

    if old_state and old_state.account_id:
        old_effect = _signed_effect(old_state)
        if old_effect != ZERO:
            deltas[old_state.account_id] = deltas.get(old_state.account_id, ZERO) - old_effect

    if new_state and new_state.account_id:
        new_effect = _signed_effect(new_state)
        if new_effect != ZERO:
            deltas[new_state.account_id] = deltas.get(new_state.account_id, ZERO) + new_effect

    return {aid: amt.quantize(PREC) for aid, amt in deltas.items() if amt != ZERO}


def _idempotency_key(event_type: str, *, account_id: int, tx_id: int | None, reason: str, payload: dict) -> str:
    """
    Key determinística para no duplicar eventos.
    """
    base = {
        "event_type": event_type,
        "account_id": account_id,
        "tx_id": tx_id,
        "reason": reason,
        "payload": payload,
    }
    raw = json.dumps(base, sort_keys=True, default=str)
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"{event_type}:{account_id}:{tx_id}:{h}"


def apply_account_balance_deltas(
    *,
    deltas: dict[int, Decimal],
    tx=None,
    reason: str,
    publish_bus_after_commit: bool = True,  # si usas bus local hoy, útil
) -> list[dict]:
    """
    Aplica deltas a Account.balance (cache incremental) con lock por fila.
    Además:
    - encola outbox idempotente
    - on_commit hace ping realtime (patrón 2)
    - opcional: publica al bus local después de commit
    """
    if not deltas:
        return []

    from finance.accounts.models.account import Account  # local import evita ciclos

    changes: list[dict] = []
    now = timezone.now()

    with transaction.atomic():
        accounts = {acc.pk: acc for acc in Account.objects.select_for_update().filter(pk__in=deltas.keys())}

        # Recolectamos pings y eventos para ejecutar after commit
        pings: list[dict] = []
        outbox_events = []

        for account_id, delta in deltas.items():
            account = accounts.get(account_id)
            if account is None:
                continue

            # Guardrails: no romper tu lógica, pero evitar inconsistencias
            if account.is_closed:
                continue
            if account.read_only:
                # si quieres permitir deltas “importados” en read_only, lo manejas en flags
                continue

            old_balance = _decimal(account.balance)
            new_balance = (old_balance + _decimal(delta)).quantize(PREC)

            if new_balance == old_balance:
                continue

            account.balance = new_balance
            update_fields = ["balance", "updated_at"]

            if tx is not None:
                account.last_activity_at = now
                account.last_transaction_amount = _decimal(getattr(tx, "amount", ZERO))
                account.last_transaction_type = getattr(tx, "type", "") or ""
                update_fields.extend(["last_activity_at", "last_transaction_amount", "last_transaction_type"])

            account.save(update_fields=update_fields)

            change = {
                "account": account,
                "old_balance": old_balance,
                "new_balance": new_balance,
                "delta": (new_balance - old_balance).quantize(PREC),
                "reason": reason,
            }
            changes.append(change)

            # ===== OUTBOX EVENT =====
            payload = {
                "account_id": account.pk,
                "owner_id": account.owner_id,
                "currency": account.currency,
                "old_balance": str(old_balance),
                "new_balance": str(new_balance),
                "delta": str(change["delta"]),
                "reason": reason,
            }
            if tx is not None:
                payload.update(
                    {
                        "transaction_id": getattr(tx, "pk", None),
                        "transaction_type": getattr(tx, "type", None),
                        "transaction_amount": str(getattr(tx, "amount", None)),
                    }
                )

            event_type = "accounts.balance.updated.v1"
            idem = _idempotency_key(
                event_type,
                account_id=account.pk,
                tx_id=getattr(tx, "pk", None),
                reason=reason,
                payload=payload,
            )

            event = enqueue_domain_event(
                aggregate_type="account",
                aggregate_id=str(account.pk),
                event_type=event_type,
                idempotency_key=idem,
                payload=payload,
                metadata={
                    "source": "accounts.use_cases",
                    "context": "accounts",
                },
            )
            outbox_events.append(event)

            # ===== REALTIME PING (Patrón 2) =====
            pings.append(
                {
                    "owner_id": account.owner_id,
                    "account_id": account.pk,
                    "event": "account.balance.changed",
                    "extra": {"reason": reason},
                }
            )

        def _after_commit():
            # 1) pings livianos
            for p in pings:
                ping_account_changed(**p)

            # 2) (opcional) publicar al bus local desde outbox
            if publish_bus_after_commit:
                for ev in outbox_events:
                    publish_after_commit(ev)

        transaction.on_commit(_after_commit)

    return changes


def apply_transaction_balance_change(
    tx,
    *,
    old_state: TransactionBalanceState | None,
    reason: str,
    publish_bus_after_commit: bool = True,
) -> list[dict]:
    new_state = build_state_from_transaction(tx)
    deltas = calculate_account_balance_deltas(old_state=old_state, new_state=new_state)
    return apply_account_balance_deltas(
        deltas=deltas,
        tx=tx,
        reason=reason,
        publish_bus_after_commit=publish_bus_after_commit,
    )


def apply_transaction_balance_delete(
    tx,
    *,
    reason: str = "tx_deleted",
    publish_bus_after_commit: bool = True,
) -> list[dict]:
    old_state = build_state_from_transaction(tx)
    deltas = calculate_account_balance_deltas(old_state=old_state, new_state=None)
    return apply_account_balance_deltas(
        deltas=deltas,
        tx=tx,
        reason=reason,
        publish_bus_after_commit=publish_bus_after_commit,
    )
