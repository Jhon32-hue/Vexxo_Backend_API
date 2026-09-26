from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from finance.accounts.models import Account
from finance.transactions.Models import Transaction, ManualTransactionReceipt, TransactionDomainEventOutbox
from finance.transactions.Views.transactions_views import TransactionViewSet


class ManualIdempotencyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="manual-idem", password="local-test")
        self.account = Account.objects.create(owner=self.user, name="Local", currency="COP")
        self.payload = {"account": self.account.pk, "type": "expense", "amount": "1000.00", "date": "2026-09-25"}

    def post(self, key="manual-test", payload=None):
        request = APIRequestFactory().post("/transactions/", payload or self.payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
        force_authenticate(request, user=self.user)
        return TransactionViewSet.as_view({"post": "create"})(request)

    def test_replay_creates_one_transaction(self):
        first = self.post()
        self.assertEqual(first.status_code, 201, first.data)
        events = TransactionDomainEventOutbox.objects.count()
        self.account.refresh_from_db()
        balance = self.account.balance
        second = self.post()
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(ManualTransactionReceipt.objects.count(), 1)
        self.assertEqual(TransactionDomainEventOutbox.objects.count(), events)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, balance)

    def test_changed_payload_conflicts(self):
        self.assertEqual(self.post().status_code, 201)
        response = self.post(payload={**self.payload, "amount": "2000.00"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_deleted_transaction_is_not_recreated(self):
        self.post()
        Transaction.objects.all().delete()
        self.assertEqual(self.post().status_code, 410)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_invalid_request_does_not_reserve_key(self):
        self.assertEqual(self.post(payload={**self.payload, "account": 0}).status_code, 400)
        self.assertFalse(ManualTransactionReceipt.objects.exists())
        self.assertEqual(self.post().status_code, 201)
