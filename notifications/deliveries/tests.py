from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from notifications.deliveries.models import NotificationCategory
from notifications.deliveries.services import create_notification_delivery

User = get_user_model()


class NotificationDeliveryApiTests(TestCase):
    endpoint = "/api/notifications/deliveries/entregas-notificacion/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="notification-owner",
            email="notification-owner@example.com",
            password="secret123",
        )
        self.other = User.objects.create_user(
            username="notification-other",
            email="notification-other@example.com",
            password="secret123",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_list_exposes_product_identity_without_other_users(self):
        own = create_notification_delivery(
            owner=self.user,
            notification_key="finance.transaction.recorded",
            category=NotificationCategory.FINANCE,
            priority="normal",
            template_key="finance.transaction.recorded",
            action_path="/transactions",
            title="Gasto registrado",
            message="Tu gasto quedo registrado.",
        )
        create_notification_delivery(
            owner=self.other,
            notification_key="security.device.registered",
            category=NotificationCategory.SECURITY,
            priority="high",
            title="Nuevo dispositivo",
            message="Nuevo acceso.",
        )

        response = self.client.get(f"{self.endpoint}?category=finance")

        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], own.pk)
        self.assertEqual(rows[0]["notification_key"], "finance.transaction.recorded")
        self.assertEqual(rows[0]["action_path"], "/transactions")

    def test_catalog_is_versioned_and_contains_shared_expenses(self):
        response = self.client.get(f"{self.endpoint}catalog/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["version"], 1)
        keys = {item["notification_key"] for item in response.data["items"]}
        self.assertIn("identity.welcome", keys)
        self.assertIn("finance.transaction.recorded", keys)
        self.assertIn("collaboration.shared_expense.invited", keys)
