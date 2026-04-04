from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from common.domain_events import EventContext, VexxoAppDomainEvent
from finance.accounts.models import Account, AccountMembership
from finance.debts.models import Debt, DebtInstallment
from finance.transactions.Models.outbox import TransactionDomainEventOutbox
from finance.transactions.Models.transacciones import Transaction
from finance.transactions.Views.transactions_views import TransactionViewSet
from finance.transactions.domain_events import (
    TransactionDomainEventTypes,
    build_transaction_payload,
    serialize_transaction_state,
)
from finance.transactions.event_handlers import handle_transaction_side_effects

User = get_user_model()


class TransactionEventActorTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="tx-actor",
            email="tx-actor@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Actor",
            currency="COP",
        )

    def _create_transaction(self):
        view = TransactionViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/finance/transactions/transactions/",
            {
                "account": self.account.pk,
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "12000.00",
                "date": "2026-04-03",
                "notes": "Compra semanal",
                "confirmed": True,
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, 201)
        return Transaction.objects.get(pk=response.data["id"])

    def test_create_update_delete_events_capture_actor_user_id(self):
        tx = self._create_transaction()

        created_event = TransactionDomainEventOutbox.objects.filter(
            event_type=TransactionDomainEventTypes.TRANSACTION_CREATED,
            aggregate_id=str(tx.pk),
        ).latest("occurred_at")
        self.assertEqual(created_event.payload["actor_user_id"], str(self.user.id))

        update_view = TransactionViewSet.as_view({"patch": "partial_update"})
        update_request = self.factory.patch(
            f"/finance/transactions/transactions/{tx.pk}/",
            {"notes": "Compra semanal actualizada"},
            format="json",
        )
        force_authenticate(update_request, user=self.user)
        update_response = update_view(update_request, pk=tx.pk)
        self.assertEqual(update_response.status_code, 200)

        updated_event = TransactionDomainEventOutbox.objects.filter(
            event_type=TransactionDomainEventTypes.TRANSACTION_UPDATED,
            aggregate_id=str(tx.pk),
        ).latest("occurred_at")
        self.assertEqual(updated_event.payload["actor_user_id"], str(self.user.id))

        delete_view = TransactionViewSet.as_view({"delete": "destroy"})
        delete_request = self.factory.delete(f"/finance/transactions/transactions/{tx.pk}/")
        force_authenticate(delete_request, user=self.user)
        delete_response = delete_view(delete_request, pk=tx.pk)
        self.assertEqual(delete_response.status_code, 204)

        deleted_event = TransactionDomainEventOutbox.objects.filter(
            event_type=TransactionDomainEventTypes.TRANSACTION_DELETED,
            aggregate_id=str(tx.pk),
        ).latest("occurred_at")
        self.assertEqual(deleted_event.payload["actor_user_id"], str(self.user.id))


class TransactionSharedAccessTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(
            username="owner-shared",
            email="owner-shared@example.com",
            password="secret123",
            plan="pro",
        )
        self.collaborator = User.objects.create_user(
            username="member-shared",
            email="member-shared@example.com",
            password="secret123",
            plan="free",
        )
        self.account = Account.objects.create(
            owner=self.owner,
            name="Cuenta Compartida",
            currency="COP",
            ownership="shared",
        )
        self.account.ensure_owner_membership()
        AccountMembership.objects.create(
            account=self.account,
            user=self.collaborator,
            role="member",
            access_mode="full",
            can_post_transactions=True,
            is_active=True,
        )
        self.tx = Transaction.objects.create(
            owner=self.owner,
            account=self.account,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.POSTED,
            amount=Decimal("45000.00"),
            date=date(2026, 4, 3),
            notes="Mercado compartido",
            confirmed=True,
        )

    def test_member_can_list_shared_transactions_with_scope_shared(self):
        view = TransactionViewSet.as_view({"get": "list"})
        request = self.factory.get("/finance/transactions/transactions/?scope=shared")
        force_authenticate(request, user=self.collaborator)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        ids = {str(item["id"]) for item in response.data}
        self.assertIn(str(self.tx.pk), ids)

    def test_member_creates_transaction_into_owner_ledger(self):
        view = TransactionViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/finance/transactions/transactions/",
            {
                "account": self.account.pk,
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "10000.00",
                "date": "2026-04-04",
                "notes": "Taxi compartido",
                "confirmed": True,
            },
            format="json",
        )
        force_authenticate(request, user=self.collaborator)
        response = view(request)

        self.assertEqual(response.status_code, 201)
        tx = Transaction.objects.get(pk=response.data["id"])
        self.assertEqual(tx.owner_id, self.owner.id)
        event = TransactionDomainEventOutbox.objects.filter(
            event_type=TransactionDomainEventTypes.TRANSACTION_CREATED,
            aggregate_id=str(tx.pk),
        ).latest("occurred_at")
        self.assertTrue(event.payload["shared_account"])
        self.assertEqual(event.payload["actor_user_id"], str(self.collaborator.id))


class TransactionFinancialReconciliationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tx-reconcile",
            email="tx-reconcile@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Deuda",
            currency="COP",
        )
        self.debt = Debt.objects.create(
            owner=self.user,
            name="Prestamo",
            principal=Decimal("100.00"),
            currency="COP",
            start_date=date(2026, 4, 1),
            total_installments=1,
            term_months=1,
            status="active",
        )
        self.installment = DebtInstallment.objects.filter(debt=self.debt).order_by("number").first()
        if not self.installment:
            self.installment = DebtInstallment.objects.create(
                owner=self.user,
                debt=self.debt,
                number=1,
                due_date=date(2026, 4, 10),
                amount_due=Decimal("100.00"),
            )

    def _event(self, event_type: str, payload: dict) -> VexxoAppDomainEvent:
        return VexxoAppDomainEvent(
            type=event_type,
            context=EventContext.TRANSACTIONS,
            payload=payload,
            metadata={"source": "finance.transactions.tests"},
        )

    def test_financial_update_reconciles_debt_payments(self):
        tx = Transaction.objects.create(
            owner=self.user,
            account=self.account,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.POSTED,
            amount=Decimal("100.00"),
            date=date(2026, 4, 3),
            debt=self.debt,
            installment=self.installment,
            confirmed=True,
        )

        created_payload = build_transaction_payload(tx, before={})
        handle_transaction_side_effects(self._event(TransactionDomainEventTypes.TRANSACTION_CREATED, created_payload))
        self.installment.refresh_from_db()
        self.assertEqual(self.installment.paid_amount, Decimal("100.00"))
        self.assertEqual(self.installment.status, "paid")

        before = serialize_transaction_state(tx)
        tx.amount = Decimal("40.00")
        tx.save(update_fields=["amount", "updated_at"])

        financial_payload = build_transaction_payload(tx, before=before)
        handle_transaction_side_effects(
            self._event(TransactionDomainEventTypes.TRANSACTION_FINANCIAL_UPDATED, financial_payload)
        )

        self.installment.refresh_from_db()
        self.debt.refresh_from_db()
        self.assertEqual(self.installment.paid_amount, Decimal("40.00"))
        self.assertEqual(self.installment.status, "partial")
        self.assertEqual(self.debt.status, "active")
