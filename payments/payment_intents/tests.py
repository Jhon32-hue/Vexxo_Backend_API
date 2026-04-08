from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from payments.payment_intents.domain_events import (
    build_payment_intent_payload,
    get_payment_event_catalog,
)
from payments.payment_intents.models import PaymentIntent

User = get_user_model()


class PaymentIntentDomainEventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="payment-user",
            email="payment@example.com",
            password="secret123",
            plan="free",
        )

    def test_build_payment_payload_includes_failure_fields(self):
        payment_intent = PaymentIntent.objects.create(
            owner=self.user,
            idempotency_key="idem-1",
            amount="25000.00",
            currency="COP",
            provider="wompi",
            failure_code="insufficient_funds",
            failure_message="Fondos insuficientes",
        )

        payload = build_payment_intent_payload(
            payment_intent,
            change="payment_intent_failed",
        )

        self.assertEqual(payload["failure_code"], "insufficient_funds")
        self.assertEqual(payload["failure_message"], "Fondos insuficientes")

    def test_payment_catalog_declares_notification_listener_for_requires_action(self):
        catalog = get_payment_event_catalog()
        event = next(item for item in catalog if item["event_type"] == "payments.intent.requires_action.v1")

        self.assertIn("notifications.handle_payment_intent_requires_action", event["current_local_listeners"])

    def test_payment_catalog_declares_notification_listener_for_failed(self):
        catalog = get_payment_event_catalog()
        event = next(item for item in catalog if item["event_type"] == "payments.intent.failed.v1")

        self.assertIn("notifications.handle_payment_intent_failed", event["current_local_listeners"])
