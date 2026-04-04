from __future__ import annotations

from decimal import Decimal

from django.db import transaction as db_tx
from django.utils import timezone

from alerts.alerts.services import create_alert
from finance.accounts.models.account import Account
from finance.transactions.Models.transacciones import ScheduledPayment, Transaction
from finance.transactions.domain_events import TransactionDomainEventTypes
from finance.transactions.event_service import publish_transaction_event_after_commit
from finance.transactions.transaction_state_service import is_transaction_countable_for_ledger
from finance.transactions.utils_limits import account_month_expense_total


@db_tx.atomic
def reassign_transaction_account(*, tx: Transaction, new_account: Account, actor) -> Transaction:
    previous_account_id = tx.account_id
    tx.account = new_account
    tx.save(update_fields=["account", "updated_at"])
    publish_transaction_event_after_commit(
        event_type=TransactionDomainEventTypes.TRANSACTION_ACCOUNT_REASSIGNED,
        payload={
            "transaction_id": str(tx.pk),
            "owner_id": str(tx.owner_id),
            "previous_account_id": str(previous_account_id) if previous_account_id else "",
            "account_id": str(tx.account_id),
            "actor_id": str(actor.id),
        },
        metadata={"source": "finance.transactions.transaction_actions_service.reassign_transaction_account"},
    )
    return tx


@db_tx.atomic
def confirm_transaction(*, tx: Transaction, actor) -> Transaction:
    if tx.confirmed and tx.status in [Transaction.Status.POSTED, Transaction.Status.RECONCILED]:
        return tx
    tx.confirmed = True
    if tx.status == Transaction.Status.PENDING:
        tx.status = Transaction.Status.POSTED
    tx.save(update_fields=["confirmed", "status", "updated_at"])
    return tx


@db_tx.atomic
def add_transaction_comment(*, tx: Transaction, text: str, actor) -> Transaction:
    comments = list(tx.comments or [])
    comments.append(
        {
            "author_id": actor.id,
            "text": text,
            "created_at": timezone.now().isoformat(),
        }
    )
    tx.comments = comments
    tx.save(update_fields=["comments", "updated_at"])
    return tx


@db_tx.atomic
def register_transaction_reimbursement(*, expense: Transaction, amount=None, date=None, notes: str = "", actor=None) -> Transaction:
    if expense.reimbursed:
        return expense.reimbursement_transaction
    resolved_amount = Decimal(str(amount)) if amount is not None else expense.amount
    resolved_date = date or timezone.now().date()
    income_tx = Transaction.objects.create(
        owner=expense.owner,
        type=Transaction.Type.INCOME,
        status=Transaction.Status.POSTED,
        amount=resolved_amount,
        date=resolved_date,
        account=expense.account,
        vendor=expense.vendor,
        source="reimbursement",
        notes=notes or f"Reembolso de gasto #{expense.id}",
        confirmed=True,
    )
    expense.reimbursed = True
    expense.reimbursement_transaction = income_tx
    expense.save(update_fields=["reimbursed", "reimbursement_transaction", "updated_at"])
    publish_transaction_event_after_commit(
        event_type=TransactionDomainEventTypes.TRANSACTION_REIMBURSEMENT_RECORDED,
        payload={
            "transaction_id": str(expense.pk),
            "owner_id": str(expense.owner_id),
            "reimbursement_transaction_id": str(income_tx.pk),
            "actor_id": str(getattr(actor, "id", "") or ""),
        },
        metadata={"source": "finance.transactions.transaction_actions_service.register_transaction_reimbursement"},
    )
    return income_tx


@db_tx.atomic
def materialize_transaction_from_legacy_scheduled_payment(*, scheduled_payment: ScheduledPayment) -> Transaction:
    if scheduled_payment.status == ScheduledPayment.Status.PAID:
        raise ValueError("Este pago programado ya esta marcado como pagado.")
    tx = Transaction.objects.create(
        owner=scheduled_payment.owner,
        type=Transaction.Type.EXPENSE,
        status=Transaction.Status.POSTED,
        amount=scheduled_payment.amount,
        date=scheduled_payment.due_date,
        account=scheduled_payment.account,
        category=scheduled_payment.category,
        vendor=scheduled_payment.vendor,
        debt=scheduled_payment.debt,
        installment=scheduled_payment.installment,
        scheduled_payment=scheduled_payment,
        source="scheduled_payment",
        notes=f"Pago programado legacy: {scheduled_payment.name}",
        confirmed=True,
    )
    tx.tags.set(scheduled_payment.tags.all())
    scheduled_payment.status = ScheduledPayment.Status.PAID
    scheduled_payment.save(update_fields=["status"])
    return tx


def apply_transaction_to_debt_if_any(tx: Transaction) -> None:
    if tx.type != Transaction.Type.EXPENSE or not tx.debt_id or not is_transaction_countable_for_ledger(tx):
        return
    from finance.debts.services import apply_payment_to_debt

    installment = tx.installment if tx.installment_id else None
    apply_payment_to_debt(
        debt=tx.debt,
        amount=Decimal(tx.amount),
        pay_date=tx.date,
        installment=installment,
    )


def mark_legacy_scheduled_payment_paid_if_needed(tx: Transaction) -> None:
    if not tx.scheduled_payment_id or not is_transaction_countable_for_ledger(tx):
        return
    sp = ScheduledPayment.objects.filter(pk=tx.scheduled_payment_id).first()
    if not sp or sp.status == ScheduledPayment.Status.PAID:
        return
    sp.status = ScheduledPayment.Status.PAID
    sp.save(update_fields=["status"])


def reconcile_legacy_scheduled_payment_state(*, scheduled_payment_id) -> None:
    if not scheduled_payment_id:
        return
    sp = ScheduledPayment.objects.filter(pk=scheduled_payment_id).first()
    if not sp:
        return
    has_countable_tx = Transaction.objects.filter(
        scheduled_payment_id=scheduled_payment_id,
        confirmed=True,
        affects_balance=True,
        status__in=[Transaction.Status.POSTED, Transaction.Status.RECONCILED],
    ).exists()
    desired_status = ScheduledPayment.Status.PAID if has_countable_tx else ScheduledPayment.Status.PENDING
    if sp.status != desired_status:
        sp.status = desired_status
        sp.save(update_fields=["status"])


def reconcile_transaction_financial_update(*, tx: Transaction, before: dict | None = None) -> None:
    before = before or {}
    debt_ids = {
        str(before.get("debt_id") or "").strip(),
        str(getattr(tx, "debt_id", "") or "").strip(),
    }
    debt_ids.discard("")
    if debt_ids:
        from finance.debts.models import Debt
        from finance.debts.services import reconcile_debt_payments

        for debt_id in debt_ids:
            debt = Debt.objects.filter(pk=debt_id).first()
            if debt:
                reconcile_debt_payments(debt)

    scheduled_ids = {
        str(before.get("scheduled_payment_id") or "").strip(),
        str(getattr(tx, "scheduled_payment_id", "") or "").strip(),
    }
    scheduled_ids.discard("")
    for scheduled_payment_id in scheduled_ids:
        reconcile_legacy_scheduled_payment_state(scheduled_payment_id=scheduled_payment_id)


def create_over_limit_alert_if_needed(tx: Transaction) -> None:
    if tx.type != Transaction.Type.EXPENSE or not is_transaction_countable_for_ledger(tx):
        return
    account = tx.account
    monthly_limit = getattr(account, "monthly_expense_limit", None)
    lock_on_limit = getattr(account, "lock_on_limit", False)
    if not monthly_limit or lock_on_limit:
        return
    month_total = account_month_expense_total(account, tx.date)
    if Decimal(month_total) <= Decimal(monthly_limit):
        return
    from alerts.alerts.models.alerts import Alert

    if Alert.objects.filter(owner=tx.owner, type="over_spend", payload__transaction_id=tx.pk).exists():
        return
    create_alert(
        owner=tx.owner,
        type="over_spend",
        title=f"Limite mensual excedido en {account.name}",
        message=f"Has superado el limite mensual de gasto para la cuenta {account.name}.",
        payload={
            "account_id": account.pk,
            "account_name": account.name,
            "month_total": float(month_total),
            "limit": float(monthly_limit),
            "currency": account.currency,
            "transaction_id": tx.pk,
            "date": tx.date.isoformat(),
        },
        source="finance.transactions.transaction_actions_service.create_over_limit_alert_if_needed",
    )
