"""
Use cases de balance incremental para accounts.

Descripcion general:
- aplica cambios incrementales al cache `Account.balance`
- traduce mutaciones de transacciones en cambios contables y eventos del dominio

Analisis detallado:
- el objetivo principal es evitar recalculos completos del ledger ante cada
  cambio de transaccion
- aun asi, el modulo sigue publicando eventos `accounts.balance.updated.v1`
  para que alertas, notificaciones, dashboards y servicios externos reaccionen
- este flujo esta preparado para convivir con outbox, bus local y futuros
  consumidores en Pub/Sub sin cambiar el contrato funcional

Que se puede hacer despues:
- agregar metricas de drift entre incremental y full recalc
- introducir retries o colas si el throughput de transacciones crece mucho
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from finance.accounts.services.event_service import publish_after_commit
from finance.accounts.services.outbox_service import enqueue_account_balance_updated_event
from finance.accounts.services.realtime_services import ping_account_changed
from finance.transactions.constants import CREDIT_TYPES, DEBIT_TYPES, POSTED_STATUSES

ZERO = Decimal("0.00")
PREC = Decimal("0.000001")


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
    if state is None or not state.account_id:
        return ZERO
    if not state.confirmed or not state.affects_balance:
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
    deltas: dict[int, Decimal] = {}

    if old_state and old_state.account_id:
        old_effect = _signed_effect(old_state)
        if old_effect != ZERO:
            deltas[old_state.account_id] = deltas.get(old_state.account_id, ZERO) - old_effect

    if new_state and new_state.account_id:
        new_effect = _signed_effect(new_state)
        if new_effect != ZERO:
            deltas[new_state.account_id] = deltas.get(new_state.account_id, ZERO) + new_effect

    return {account_id: amount.quantize(PREC) for account_id, amount in deltas.items() if amount != ZERO}


def apply_account_balance_deltas(
    *,
    deltas: dict[int, Decimal],
    tx=None,
    reason: str,
    publish_bus_after_commit: bool = True,
) -> list[dict]:
    if not deltas:
        return []

    from finance.accounts.models.account import Account

    changes: list[dict] = []
    now = timezone.now()

    with transaction.atomic():
        accounts = {
            account.pk: account
            for account in Account.objects.select_for_update().filter(pk__in=deltas.keys())
        }

        pings: list[dict] = []
        outbox_events = []

        for account_id, delta in deltas.items():
            account = accounts.get(account_id)
            if account is None or account.is_closed:
                continue
            if account.read_only:
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

            event = enqueue_account_balance_updated_event(
                account=account,
                old_balance=old_balance,
                new_balance=new_balance,
                reason=reason,
                transaction_id=getattr(tx, "pk", None),
                metadata={"source": "accounts.use_cases"},
            )
            outbox_events.append(event)

            pings.append(
                {
                    "owner_id": account.owner_id,
                    "account_id": account.pk,
                    "event": "account.balance.changed",
                    "extra": {"reason": reason},
                }
            )

        def _after_commit():
            for ping in pings:
                ping_account_changed(**ping)

            if publish_bus_after_commit:
                for event in outbox_events:
                    publish_after_commit(event)

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
