from __future__ import annotations

from dataclasses import dataclass

from alerts.alerts.models.outbox import AlertDomainEventOutbox
from common.domain_events import EventContext
from finance.accounts.models import DomainEventOutbox
from finance.debts.models import DebtDomainEventOutbox
from finance.transactions.Models.outbox import TransactionDomainEventOutbox
from identity.eventing.models import IdentityDomainEventOutbox
from payments.payment_intents.models import PaymentDomainEventOutbox
from planning.goals.models import GoalDomainEventOutbox
from documents.ocr_requests.models import DocumentDomainEventOutbox
from social.shared_expenses.models import SharedExpenseDomainEventOutbox


@dataclass(frozen=True)
class OutboxRuntimeSpec:
    model: type
    context: EventContext
    command_name: str = ""


OUTBOX_SPECS = {
    "accounts": OutboxRuntimeSpec(
        model=DomainEventOutbox,
        context=EventContext.ACCOUNTS,
        command_name="accounts_publish_outbox",
    ),
    "transactions": OutboxRuntimeSpec(
        model=TransactionDomainEventOutbox,
        context=EventContext.TRANSACTIONS,
        command_name="transactions_publish_outbox",
    ),
    "alerts": OutboxRuntimeSpec(
        model=AlertDomainEventOutbox,
        context=EventContext.ALERTS,
        command_name="alerts_publish_outbox",
    ),
    "identity": OutboxRuntimeSpec(
        model=IdentityDomainEventOutbox,
        context=EventContext.IDENTITY,
        command_name="identity_publish_outbox",
    ),
    "payments": OutboxRuntimeSpec(
        model=PaymentDomainEventOutbox,
        context=EventContext.PAYMENTS,
        command_name="payments_publish_outbox",
    ),
    "debts": OutboxRuntimeSpec(model=DebtDomainEventOutbox, context=EventContext.DEBTS),
    "goals": OutboxRuntimeSpec(model=GoalDomainEventOutbox, context=EventContext.GOALS),
    "documents": OutboxRuntimeSpec(model=DocumentDomainEventOutbox, context=EventContext.DOCUMENTS),
    "shared_expenses": OutboxRuntimeSpec(
        model=SharedExpenseDomainEventOutbox,
        context=EventContext.SHARED_EXPENSES,
    ),
}
