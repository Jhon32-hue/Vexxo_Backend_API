from __future__ import annotations

import hashlib
import hmac
import json

from django.test import SimpleTestCase, override_settings

from payments.payment_intents.adapters import get_payment_provider_adapter
from payments.payment_intents.serializers import PaymentProviderCallbackSerializer


class PaymentIntentSerializerContractTests(SimpleTestCase):
    def test_provider_callback_rejects_non_object_payload(self):
        serializer = PaymentProviderCallbackSerializer(
            data={
                "provider": "wompi",
                "payload": ["unexpected", "list"],
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("payload", serializer.errors)


class PaymentProviderSignatureTests(SimpleTestCase):
    @override_settings(PAYMENTS_PROVIDER_SETTINGS={"generic": {"callback_secret": ""}})
    def test_missing_secret_fails_closed(self):
        adapter = get_payment_provider_adapter("generic")
        self.assertFalse(adapter.verify_callback({"status": "succeeded"}, headers={}))

    @override_settings(PAYMENTS_PROVIDER_SETTINGS={"generic": {"callback_secret": "local-secret"}})
    def test_valid_hmac_is_accepted(self):
        payload = {"status": "succeeded", "payment_intent_id": 1}
        body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        signature = hmac.new(b"local-secret", body, hashlib.sha256).hexdigest()
        adapter = get_payment_provider_adapter("generic")
        self.assertTrue(
            adapter.verify_callback(payload, headers={"X-Vexxo-Provider-Signature": signature})
        )
