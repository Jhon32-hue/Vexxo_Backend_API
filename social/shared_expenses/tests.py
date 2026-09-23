from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from common.domain_events import EventNames
from finance.accounts.models import Account
from finance.transactions.Models import Transaction, TransactionParticipant
from social.shared_expenses.models import SharedExpense, SharedExpenseDomainEventOutbox, SharedExpenseSettlement
from social.shared_expenses.services import calculate_shares

User = get_user_model()


class SharedExpenseAllocationTests(TestCase):
    def test_equal_split_assigns_rounding_residue_deterministically(self):
        result = calculate_shares(
            total=Decimal("100.00"),
            method=SharedExpense.SplitMethod.EQUAL,
            specs=[
                {"is_payer": True, "display_name": "Owner"},
                {"display_name": "B"},
                {"display_name": "C"},
            ],
        )

        self.assertEqual([row["expected_amount"] for row in result], [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        self.assertEqual(sum(row["expected_amount"] for row in result), Decimal("100.00"))

    def test_percentage_split_requires_exactly_one_hundred(self):
        with self.assertRaisesMessage(Exception, "porcentajes deben sumar exactamente 100"):
            calculate_shares(
                total=Decimal("100.00"),
                method=SharedExpense.SplitMethod.PERCENTAGE,
                specs=[
                    {"is_payer": True, "display_name": "Owner", "percentage": "60"},
                    {"display_name": "B", "percentage": "39"},
                ],
            )


class SharedExpenseApiTests(TestCase):
    endpoint = "/api/social/shared-expenses/shared-expenses/"

    def setUp(self):
        self.owner = User.objects.create_user(
            username="shared-owner",
            email="owner@example.com",
            password="secret123",
            preferred_currency="COP",
        )
        self.participant = User.objects.create_user(
            username="shared-participant",
            email="participant@example.com",
            password="secret123",
            preferred_currency="COP",
        )
        self.outsider = User.objects.create_user(
            username="shared-outsider",
            email="outsider@example.com",
            password="secret123",
        )
        self.owner_account = Account.objects.create(owner=self.owner, name="Owner account", currency="COP")
        self.participant_account = Account.objects.create(
            owner=self.participant,
            name="Participant account",
            currency="COP",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _payload(self, amount="100.00"):
        return {
            "transaction_payload": {
                "account": self.owner_account.pk,
                "type": "expense",
                "status": "posted",
                "amount": amount,
                "date": "2026-09-22",
                "description": "Cena compartida",
                "confirmed": True,
            },
            "split_method": "equal",
            "shares": [
                {
                    "participant_user": self.owner.pk,
                    "is_payer": True,
                    "display_name": "Owner",
                },
                {
                    "participant_user": self.participant.pk,
                    "display_name": "Participant",
                    "email": self.participant.email,
                },
            ],
        }

    def _create(self, *, key="shared-create-1", payload=None):
        return self.client.post(
            self.endpoint,
            payload or self._payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_X_REQUEST_ID=f"request-{key}",
        )

    def test_create_is_atomic_idempotent_and_does_not_write_foreign_ledger(self):
        first = self._create()
        self.assertEqual(first.status_code, 201, first.data)
        second = self._create()
        self.assertEqual(second.status_code, 201, second.data)

        expense = SharedExpense.objects.get()
        self.assertEqual(SharedExpense.objects.count(), 1)
        self.assertEqual(Transaction.objects.filter(owner=self.owner).count(), 1)
        self.assertEqual(expense.shares.count(), 2)
        self.assertEqual(sum(expense.shares.values_list("expected_amount", flat=True)), Decimal("100.00"))
        self.assertEqual(TransactionParticipant.objects.count(), 0)
        self.assertTrue(
            SharedExpenseDomainEventOutbox.objects.filter(event_type=EventNames.SHARED_EXPENSE_CREATED).exists()
        )
        invitation = SharedExpenseDomainEventOutbox.objects.get(
            event_type=EventNames.SHARED_EXPENSE_SHARE_INVITED
        )
        self.assertEqual(invitation.payload["participant_user_id"], self.participant.pk)
        self.assertEqual(invitation.payload["currency"], "COP")

    def test_reusing_idempotency_key_with_different_payload_conflicts(self):
        self.assertEqual(self._create().status_code, 201)
        response = self._create(payload=self._payload(amount="120.00"))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "shared_expense_conflict")

    def test_participant_accepts_idempotently_and_materializes_projection(self):
        created = self._create()
        expense_id = created.data["public_id"]
        share = next(row for row in created.data["shares"] if not row["is_payer"])
        self.client.force_authenticate(self.participant)
        url = f"{self.endpoint}{expense_id}/accept/"
        payload = {"share_id": share["public_id"], "base_version": created.data["version"]}

        accepted = self.client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="accept-1")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        retried = self.client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="accept-1")
        self.assertEqual(retried.status_code, 200, retried.data)
        projection = TransactionParticipant.objects.get()
        self.assertEqual(projection.linked_user, self.participant)
        self.assertEqual(projection.share_amount, Decimal("50.00"))

    def test_stale_revision_returns_authoritative_conflict(self):
        created = self._create()
        expense = SharedExpense.objects.get(public_id=created.data["public_id"])
        expense.version = 2
        expense.save(update_fields=["version"])
        response = self.client.post(
            f"{self.endpoint}{expense.public_id}/revise/",
            {
                "split_method": "equal",
                "shares": self._payload()["shares"],
                "base_version": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["current"]["version"], 2)

    def test_settlement_requires_real_owned_transaction_and_is_idempotent(self):
        created = self._create()
        expense_id = created.data["public_id"]
        share = next(row for row in created.data["shares"] if not row["is_payer"])
        self.client.force_authenticate(self.participant)
        accepted = self.client.post(
            f"{self.endpoint}{expense_id}/accept/",
            {"share_id": share["public_id"], "base_version": 1},
            format="json",
        )
        settlement_tx = Transaction.objects.create(
            owner=self.participant,
            account=self.participant_account,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.POSTED,
            amount=Decimal("50.00"),
            date=date(2026, 9, 22),
            description="Pago cena",
        )
        payload = {
            "share_id": share["public_id"],
            "transaction": settlement_tx.pk,
            "amount": "50.00",
            "base_version": accepted.data["version"],
        }
        url = f"{self.endpoint}{expense_id}/settle/"
        first = self.client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="settle-1")
        self.assertEqual(first.status_code, 200, first.data)
        second = self.client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="settle-1")
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(SharedExpenseSettlement.objects.count(), 1)
        self.assertEqual(first.data["status"], SharedExpense.Status.SETTLED)

    def test_outsider_cannot_discover_expense(self):
        created = self._create()
        self.client.force_authenticate(self.outsider)
        response = self.client.get(f"{self.endpoint}{created.data['public_id']}/")
        self.assertEqual(response.status_code, 404)
