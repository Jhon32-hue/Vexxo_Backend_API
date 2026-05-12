from __future__ import annotations

from django.test import SimpleTestCase

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
