from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from common.domain_events import EventContext, EventNames, VexxoAppDomainEvent
from notifications.deliveries.models import NotificationDelivery
from notifications.preferences.models import NotificationPreference
from notifications.listeners.event_handlers import (
    handle_account_created,
    handle_payment_intent_failed,
    handle_payment_intent_requires_action,
    materialize_catalog_notification,
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

    def test_transaction_catalog_materializes_minimized_actionable_notification(self):
        event = VexxoAppDomainEvent(
            type=EventNames.TRANSACTION_CREATED,
            context=EventContext.TRANSACTIONS,
            payload={
                "transaction_id": "tx-1",
                "owner_id": str(self.user.pk),
                "type": "expense",
                "amount": "32000.00",
                "currency": "COP",
                "description": "Mercado",
                "confirmed": True,
                "before": {"sensitive": "must-not-leak"},
                "after": {"provider_payload": "must-not-leak"},
            },
        )

        materialize_catalog_notification(event)
        delivery = NotificationDelivery.objects.get(owner=self.user)

        self.assertEqual(delivery.notification_key, "finance.transaction.recorded")
        self.assertEqual(delivery.category, "finance")
        self.assertEqual(delivery.action_path, "/transactions")
        self.assertEqual(delivery.payload["transaction_id"], "tx-1")
        self.assertNotIn("before", delivery.payload)
        self.assertNotIn("after", delivery.payload)

    def test_catalog_deduplicates_redelivery_of_same_event(self):
        event = VexxoAppDomainEvent(
            type=EventNames.SHARED_EXPENSE_SHARE_ACCEPTED,
            context=EventContext.SHARED_EXPENSES,
            payload={
                "shared_expense_id": "expense-1",
                "owner_id": str(self.user.pk),
                "share_id": "share-1",
                "version": 2,
            },
        )

        materialize_catalog_notification(event)
        materialize_catalog_notification(event)

        self.assertEqual(NotificationDelivery.objects.filter(owner=self.user).count(), 1)
        delivery = NotificationDelivery.objects.get(owner=self.user)
        self.assertEqual(delivery.category, "collaboration")
        self.assertEqual(delivery.priority, "normal")

    def test_catalog_keeps_distinct_events_for_same_aggregate(self):
        base_payload = {
            "account_id": "account-1",
            "owner_id": str(self.user.pk),
            "name": "Cuenta principal",
        }

        materialize_catalog_notification(
            VexxoAppDomainEvent(
                type=EventNames.ACCOUNT_SYNC_SUCCEEDED,
                context=EventContext.ACCOUNTS,
                payload=base_payload,
                metadata={"outbox_event_id": "outbox-1"},
            )
        )
        materialize_catalog_notification(
            VexxoAppDomainEvent(
                type=EventNames.ACCOUNT_SYNC_SUCCEEDED,
                context=EventContext.ACCOUNTS,
                payload=base_payload,
                metadata={"outbox_event_id": "outbox-2"},
            )
        )

        self.assertEqual(NotificationDelivery.objects.filter(owner=self.user).count(), 2)

    def test_catalog_respects_disabled_in_app_preference(self):
        NotificationPreference.objects.update_or_create(
            owner=self.user,
            defaults={"in_app_enabled": False},
        )
        event = VexxoAppDomainEvent(
            type=EventNames.TRANSACTION_CREATED,
            context=EventContext.TRANSACTIONS,
            payload={"owner_id": str(self.user.pk), "transaction_id": "tx-muted"},
        )

        materialize_catalog_notification(event)

        self.assertFalse(NotificationDelivery.objects.filter(owner=self.user).exists())

    def test_security_notification_bypasses_optional_in_app_preference(self):
        NotificationPreference.objects.update_or_create(
            owner=self.user,
            defaults={"in_app_enabled": False},
        )
        event = VexxoAppDomainEvent(
            type=EventNames.USER_DEVICE_REGISTERED,
            context=EventContext.IDENTITY,
            payload={"user_id": str(self.user.pk), "device_id": "device-1"},
        )

        materialize_catalog_notification(event)

        delivery = NotificationDelivery.objects.get(owner=self.user)
        self.assertEqual(delivery.notification_key, "security.device.registered")
        self.assertEqual(delivery.priority, "high")
