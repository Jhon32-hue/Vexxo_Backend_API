from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from finance.accounts.models import Account
from finance.categories.models import Category
from finance.vendors.models import Vendor
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


class PaymentIntentOwnershipTests(APITestCase):
    endpoint = "/api/payments/intents/intents/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="payment-owner",
            email="payment-owner@example.com",
            password="secret123A",
        )
        self.other_user = User.objects.create_user(
            username="payment-other",
            email="payment-other@example.com",
            password="secret123A",
        )
        self.account = Account.objects.create(owner=self.user, name="Cuenta propia")
        self.category = Category.objects.create(owner=self.user, name="Servicios", type="expense")
        self.vendor = Vendor.objects.create(owner=self.user, name="Proveedor propio")
        self.other_account = Account.objects.create(owner=self.other_user, name="Cuenta ajena")
        self.other_category = Category.objects.create(owner=self.other_user, name="Ajena", type="expense")
        self.other_vendor = Vendor.objects.create(owner=self.other_user, name="Proveedor ajeno")
        self.client.force_authenticate(self.user)

    def _payload(self, **overrides):
        payload = {
            "account": self.account.pk,
            "category": self.category.pk,
            "vendor": self.vendor.pk,
            "amount": "25000.00",
            "currency": "COP",
            "provider": "local-stub",
            "payment_type": "bill",
            "rail": "other",
            "idempotency_key": "payment-owner-idem-001",
        }
        payload.update(overrides)
        return payload

    def test_create_rejects_relations_owned_by_another_user(self):
        response = self.client.post(
            self.endpoint,
            self._payload(
                account=self.other_account.pk,
                category=self.other_category.pk,
                vendor=self.other_vendor.pk,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("account", response.data)
        self.assertIn("category", response.data)
        self.assertIn("vendor", response.data)

    def test_idempotency_is_scoped_per_owner_and_replay_is_safe(self):
        first = self.client.post(self.endpoint, self._payload(), format="json")
        replay = self.client.post(self.endpoint, self._payload(), format="json")
        mismatch = self.client.post(
            self.endpoint,
            self._payload(amount="26000.00"),
            format="json",
        )

        other_client = self.client_class()
        other_client.force_authenticate(self.other_user)
        other = other_client.post(
            self.endpoint,
            self._payload(
                account=self.other_account.pk,
                category=self.other_category.pk,
                vendor=self.other_vendor.pk,
            ),
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(replay.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("idempotency_key", mismatch.data)
        self.assertEqual(other.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(first.data["id"], other.data["id"])
        self.assertEqual(PaymentIntent.objects.filter(idempotency_key="payment-owner-idem-001").count(), 2)
