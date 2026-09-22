import json
import hashlib
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from finance.accounts.models import Account
from identity.consents.models import ConsentType, UserConsent
from integrations.open_banking.adapters import BelvoOpenBankingAdapter
from integrations.open_banking.contracts import normalize_account, normalize_transaction
from integrations.open_banking.lifecycle import (
    expire_open_banking_consents,
    quarantine_external_payload,
    reconcile_connection_account,
)
from integrations.open_banking.models import (
    OpenBankingAccountLink,
    OpenBankingConnection,
    OpenBankingExternalPayload,
    OpenBankingInstitution,
    OpenBankingWebhookReceipt,
)
from integrations.open_banking.services import process_provider_webhook
from integrations.open_banking.provider_catalog import get_provider
from support.access_history.models import SupportAccessRecord


User = get_user_model()
FIXTURES = Path(__file__).with_name("fixtures")


class OpenBankingContractTests(SimpleTestCase):
    def test_external_provider_requires_official_certification_even_with_credentials(self):
        environment = {
            "OPEN_BANKING_BELVO_CLIENT_ID": "sandbox-id",
            "OPEN_BANKING_BELVO_CLIENT_SECRET": "sandbox-secret",
            "OPEN_BANKING_BELVO_WEBHOOK_AUTHORIZATION": "sandbox-webhook",
            "SECURITY_ENCRYPTION_KEYS_JSON": '{"v1":"not-used-by-this-test"}',
        }
        with patch.dict("os.environ", environment, clear=False):
            provider = get_provider("belvo")
            self.assertTrue(provider.configured)
            self.assertFalse(provider.certified)
            self.assertFalse(provider.available)

    def test_external_provider_accepts_matching_official_vector(self):
        payload = json.dumps(
            {
                "fixture_type": "official_sandbox_vector",
                "provider": "belvo",
                "schema_version": "belvo.contract.v1",
                "webhook_vectors": [{"name": "transactions.available"}],
            },
            sort_keys=True,
        ).encode("utf-8")
        with tempfile.NamedTemporaryFile(suffix=".json") as fixture:
            fixture.write(payload)
            fixture.flush()
            environment = {
                "OPEN_BANKING_BELVO_CLIENT_ID": "sandbox-id",
                "OPEN_BANKING_BELVO_CLIENT_SECRET": "sandbox-secret",
                "OPEN_BANKING_BELVO_WEBHOOK_AUTHORIZATION": "sandbox-webhook",
                "SECURITY_ENCRYPTION_KEYS_JSON": '{"v1":"not-used-by-this-test"}',
                "OPEN_BANKING_BELVO_CERTIFIED": "true",
                "OPEN_BANKING_BELVO_OFFICIAL_FIXTURE_PATH": fixture.name,
                "OPEN_BANKING_BELVO_OFFICIAL_FIXTURE_SHA256": hashlib.sha256(payload).hexdigest(),
            }
            with patch.dict("os.environ", environment, clear=False):
                provider = get_provider("belvo")
                self.assertTrue(provider.certified)
                self.assertTrue(provider.available)

    def test_belvo_pending_and_reversed_are_canonical(self):
        fixture = json.loads((FIXTURES / "belvo_sandbox_v1.json").read_text(encoding="utf-8"))
        account = normalize_account("belvo", fixture["account"], institution_name="Banco Demo")
        pending = normalize_transaction("belvo", fixture["transactions"][0])
        reversed_row = normalize_transaction("belvo", fixture["transactions"][1])
        self.assertEqual(account["type"], "savings")
        self.assertEqual(pending["status"], "pending")
        self.assertFalse(pending["affects_balance"])
        self.assertEqual(pending["merchant_alias"], "MERCADO DEMO")
        self.assertEqual(reversed_row["status"], "reversed")

    def test_salt_edge_sign_and_counterparty_are_canonical(self):
        fixture = json.loads((FIXTURES / "salt_edge_sandbox_v1.json").read_text(encoding="utf-8"))
        row = normalize_transaction("salt_edge", fixture["transactions"][0])
        self.assertEqual(row["type"], "expense")
        self.assertEqual(row["amount"], "20000.00")
        self.assertEqual(row["counterparty_name"], "Cafe Demo SAS")

    def test_belvo_adapter_follows_opaque_pages(self):
        adapter = BelvoOpenBankingAdapter()
        connection = SimpleNamespace(external_connection_id="link-1", institution_name="Banco Demo")
        responses = [
            {"results": [{"id": "a1", "currency": "COP"}], "next": "https://sandbox/api/accounts/?page=2"},
            {"results": [{"id": "a2", "currency": "COP"}], "next": None},
        ]
        adapter._request = lambda *args, **kwargs: responses.pop(0)
        self.assertEqual([row["external_account_id"] for row in adapter.list_accounts(connection=connection)], ["a1", "a2"])


class OpenBankingLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="banking-user", email="banking@example.com", password="TestPass2026!")
        self.consent = UserConsent.objects.create(
            user=self.user,
            consent_type=ConsentType.OPEN_BANKING_DATA,
            provider="local_mock",
            status="granted",
            granted_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.institution = OpenBankingInstitution.objects.create(
            code="test-bank-co",
            name="Test Bank",
            country="CO",
        )
        self.connection = OpenBankingConnection.objects.create(
            owner=self.user,
            consent=self.consent,
            provider="local_mock",
            institution=self.institution,
            institution_name=self.institution.name,
            country="CO",
            status=OpenBankingConnection.Status.CONNECTED,
            external_connection_id="local-link-1",
            scopes=["accounts", "balances", "transactions"],
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta local",
            currency="COP",
            provider="local_mock",
            external_id="account-1",
            balance="1000.00",
        )
        self.link = OpenBankingAccountLink.objects.create(
            connection=self.connection,
            account=self.account,
            external_account_id="account-1",
        )

    def test_external_payload_is_sanitized_deduplicated_and_ttl_bound(self):
        record, created = quarantine_external_payload(
            connection=self.connection,
            account_link=self.link,
            resource_type=OpenBankingExternalPayload.ResourceType.TRANSACTIONS,
            payload=[{"id": "tx-1", "access_token": "must-not-persist"}],
            provenance="test.fixture",
        )
        duplicate, duplicate_created = quarantine_external_payload(
            connection=self.connection,
            account_link=self.link,
            resource_type=OpenBankingExternalPayload.ResourceType.TRANSACTIONS,
            payload=[{"id": "tx-1", "access_token": "must-not-persist"}],
            provenance="test.fixture",
        )
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(record.pk, duplicate.pk)
        self.assertEqual(record.sanitized_payload[0]["access_token"], "[REDACTED]")
        self.assertGreater(record.expires_at, timezone.now())

    def test_expired_consent_stops_sync_and_deactivates_links(self):
        UserConsent.objects.filter(pk=self.consent.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        result = expire_open_banking_consents()
        self.connection.refresh_from_db()
        self.link.refresh_from_db()
        self.consent.refresh_from_db()
        self.assertEqual(result["expired_connections"], 1)
        self.assertEqual(self.consent.status, "expired")
        self.assertEqual(self.connection.status, OpenBankingConnection.Status.ATTENTION_REQUIRED)
        self.assertFalse(self.link.is_active)

    def test_local_reconcile_is_repeatable_and_does_not_duplicate_case_or_adjust_ledger(self):
        first = reconcile_connection_account(account_link=self.link)
        second = reconcile_connection_account(account_link=self.link)
        self.account.refresh_from_db()
        self.assertEqual(first["status"], "difference")
        self.assertEqual(second["status"], "difference")
        self.assertEqual(first["issue_id"], second["issue_id"])
        self.assertEqual(self.connection.reconciliation_issues.count(), 1)
        self.assertEqual(self.account.balance, 1000)

    def test_out_of_order_webhook_is_rejected_without_regressing_connection(self):
        now = timezone.now()
        first, _ = process_provider_webhook(
            provider="local_mock",
            payload={
                "event_id": "evt-10",
                "event_type": "connection.connected",
                "connection_id": self.connection.external_connection_id,
                "occurred_at": now,
                "sequence": 10,
            },
            raw_body=b"event-10",
        )
        stale, _ = process_provider_webhook(
            provider="local_mock",
            payload={
                "event_id": "evt-9",
                "event_type": "connection.error",
                "connection_id": self.connection.external_connection_id,
                "occurred_at": now - timedelta(minutes=5),
                "sequence": 9,
            },
            raw_body=b"event-9",
        )
        self.connection.refresh_from_db()
        self.assertEqual(first.status, OpenBankingWebhookReceipt.Status.PROCESSED)
        self.assertEqual(stale.status, OpenBankingWebhookReceipt.Status.REJECTED)
        self.assertEqual(stale.error_code, "out_of_order")
        self.assertEqual(self.connection.status, OpenBankingConnection.Status.CONNECTED)

    def test_support_timeline_requires_reason_and_case_and_audits_access(self):
        staff = User.objects.create_superuser(username="support-user", email="support@example.com", password="TestPass2026!")
        client = APIClient()
        client.force_authenticate(staff)
        url = f"/api/internal/support/open-banking/connections/{self.connection.public_id}/timeline/"
        self.assertEqual(client.get(url).status_code, 400)
        response = client.get(
            url,
            HTTP_X_SUPPORT_REASON="Investigacion solicitada por el usuario",
            HTTP_X_SUPPORT_CASE="CASE-2026-001",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SupportAccessRecord.objects.filter(target_id=str(self.connection.public_id)).count(), 1)
