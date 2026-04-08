from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from common.domain_events import EventContext, EventNames, VexxoAppDomainEvent
from notifications.deliveries.models import NotificationDelivery
from notifications.listeners.event_handlers import (
    handle_account_created,
    handle_payment_intent_failed,
    handle_payment_intent_requires_action,
)

User = get_user_model()


class NotificationListenersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="notify-user",
            email="notify@example.com",
            password="secret123",
            plan="free",
        )

    def test_account_created_persists_in_app_delivery(self):
        event = VexxoAppDomainEvent(
            type=EventNames.ACCOUNT_CREATED,
            context=EventContext.ACCOUNTS,
            payload={
                "account_id": "acc-1",
                "owner_id": str(self.user.pk),
                "name": "Nequi",
            },
        )

        handle_account_created(event)

        delivery = NotificationDelivery.objects.get(owner=self.user)
        self.assertEqual(delivery.event_type, EventNames.ACCOUNT_CREATED)
        self.assertEqual(delivery.title, "Cuenta creada")
        self.assertIn("Nequi", delivery.message)

        handle_account_created(event)
        self.assertEqual(NotificationDelivery.objects.filter(owner=self.user).count(), 1)

    def test_payment_requires_action_persists_delivery(self):
        event = VexxoAppDomainEvent(
            type=EventNames.PAYMENT_INTENT_REQUIRES_ACTION,
            context=EventContext.PAYMENTS,
            payload={
                "payment_intent_id": "pi-1",
                "owner_id": str(self.user.pk),
                "provider": "wompi",
                "amount": "25000.00",
                "currency": "COP",
            },
        )

        handle_payment_intent_requires_action(event)

        delivery = NotificationDelivery.objects.get(owner=self.user)
        self.assertEqual(delivery.event_type, EventNames.PAYMENT_INTENT_REQUIRES_ACTION)
        self.assertEqual(delivery.title, "Tu pago requiere accion")
        self.assertIn("25000.00 COP", delivery.message)
        self.assertIn("wompi", delivery.message)

    def test_payment_failed_persists_failure_context(self):
        event = VexxoAppDomainEvent(
            type=EventNames.PAYMENT_INTENT_FAILED,
            context=EventContext.PAYMENTS,
            payload={
                "payment_intent_id": "pi-2",
                "owner_id": str(self.user.pk),
                "provider": "wompi",
                "amount": "25000.00",
                "currency": "COP",
                "failure_message": "Fondos insuficientes",
            },
        )

        handle_payment_intent_failed(event)

        delivery = NotificationDelivery.objects.get(owner=self.user)
        self.assertEqual(delivery.event_type, EventNames.PAYMENT_INTENT_FAILED)
        self.assertEqual(delivery.title, "Pago fallido")
        self.assertIn("Fondos insuficientes", delivery.message)
