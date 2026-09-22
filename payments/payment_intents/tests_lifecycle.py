from __future__ import annotations

import hashlib
import hmac
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from finance.accounts.models import Account
from payments.payment_intents.callback_service import process_payment_provider_callback
from payments.payment_intents.dispatch_service import dispatch_payment_intent
from payments.payment_intents.adapters import PaymentProviderContractError
from payments.payment_intents.models import (
    PaymentIntent,
    PaymentOperationalCase,
    PaymentProviderCallbackReceipt,
    PaymentSettlementRecord,
)


def _signature(payload: dict, secret: str = "callback-secret") -> str:
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@override_settings(PAYMENTS_LOCAL_FAKE_ENABLED=True)
class LocalFakePaymentProviderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="local-fake-payment",
            email="local-fake-payment@example.com",
            password="TestPass2026!",
        )
        self.account = Account.objects.create(owner=self.user, name="Local fake", currency="COP")

    def _intent(self, suffix: str) -> PaymentIntent:
        return PaymentIntent.objects.create(
            owner=self.user,
            account=self.account,
            amount="10000.00",
            currency="COP",
            provider="local_fake",
            internal_reference=f"internal-{suffix}",
            external_reference=f"external-{suffix}",
            idempotency_key=f"fake-{suffix}",
        )

    def test_fake_scenarios_are_deterministic(self):
        processing = dispatch_payment_intent(
            payment_intent=self._intent("processing"),
            ephemeral_payload={"scenario": "processing"},
        )
        requires_action = dispatch_payment_intent(
            payment_intent=self._intent("action"),
            ephemeral_payload={"scenario": "requires_action"},
        )
        failed = dispatch_payment_intent(
            payment_intent=self._intent("failed"),
            ephemeral_payload={"scenario": "failed"},
        )
        self.assertEqual(processing.status, PaymentIntent.Status.PROCESSING)
        self.assertTrue(processing.provider_intent_id.startswith("lf_"))
        self.assertEqual(requires_action.status, PaymentIntent.Status.REQUIRES_ACTION)
        self.assertEqual(failed.status, PaymentIntent.Status.FAILED)

    def test_fake_timeout_preserves_retryable_intent(self):
        intent = self._intent("timeout-retry")
        with self.assertRaises(PaymentProviderContractError) as context:
            dispatch_payment_intent(
                payment_intent=intent,
                ephemeral_payload={"scenario": "timeout"},
            )
        self.assertEqual(context.exception.code, "provider_timeout")
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.CREATED)

        retried = dispatch_payment_intent(
            payment_intent=intent,
            ephemeral_payload={"scenario": "succeeded"},
        )
        self.assertEqual(retried.status, PaymentIntent.Status.SUCCEEDED)


@override_settings(PAYMENTS_PROVIDER_SETTINGS={"generic": {"callback_secret": "callback-secret"}})
class PaymentCallbackLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="callback-lifecycle",
            email="callback-lifecycle@example.com",
            password="TestPass2026!",
        )
        self.account = Account.objects.create(owner=self.user, name="Callback", currency="COP")
        self.intent = PaymentIntent.objects.create(
            owner=self.user,
            account=self.account,
            amount="25000.00",
            currency="COP",
            provider="generic",
            internal_reference="callback-internal",
            external_reference="callback-external",
            provider_reference="callback-provider-ref",
            idempotency_key="callback-lifecycle",
        )

    def _callback(self, **values):
        payload = {
            "payment_intent_id": str(self.intent.pk),
            "provider_reference": "callback-provider-ref",
            **values,
        }
        return process_payment_provider_callback(
            provider="generic",
            payload=payload,
            headers={"X-Vexxo-Provider-Signature": _signature(payload)},
        )

    def test_progression_duplicate_and_late_callback(self):
        succeeded = self._callback(status="succeeded")
        settled = self._callback(
            status="settled",
            settlement_reference="settlement-001",
            amount="25000.00",
            currency="COP",
        )
        duplicate = self._callback(
            status="settled",
            settlement_reference="settlement-001",
            amount="25000.00",
            currency="COP",
        )
        late = self._callback(status="processing")
        self.intent.refresh_from_db()
        self.assertTrue(succeeded["applied"])
        self.assertTrue(settled["applied"])
        self.assertTrue(duplicate["duplicate"])
        self.assertTrue(late["transition_ignored"])
        self.assertEqual(self.intent.status, PaymentIntent.Status.SETTLED)
        self.assertEqual(PaymentSettlementRecord.objects.count(), 1)
        self.assertEqual(PaymentProviderCallbackReceipt.objects.count(), 3)

    def test_reversal_and_chargeback_open_idempotent_cases(self):
        self._callback(status="succeeded")
        reversal = self._callback(
            issue_kind="reversal",
            issue_reference="reversal-001",
            amount="25000.00",
            currency="COP",
        )
        self.assertTrue(reversal["applied"])
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.Status.REVERSED)
        chargeback = self._callback(
            issue_kind="chargeback",
            issue_reference="chargeback-001",
            amount="25000.00",
            currency="COP",
        )
        self.assertTrue(chargeback["applied"])
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.Status.DISPUTED)
        self.assertEqual(PaymentOperationalCase.objects.count(), 2)
