from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from notifications.preferences.services import get_or_create_notification_preferences

User = get_user_model()


class NotificationPreferencesTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="prefs-user",
            email="prefs@example.com",
            password="VexxoPass2026!",
            marketing_opt_in=True,
        )

    def test_preferences_bootstrap_from_marketing_opt_in(self):
        preferences = get_or_create_notification_preferences(self.user)
        self.assertTrue(preferences.email_marketing_enabled)
        self.assertTrue(preferences.newsletter_subscribed)

    def test_authenticated_user_can_update_preferences(self):
        self.client.force_authenticate(self.user)
        response = self.client.put(
            "/api/notifications/preferences/me/",
            {
                "in_app_enabled": True,
                "push_enabled": False,
                "email_notifications_enabled": True,
                "email_marketing_enabled": False,
                "newsletter_subscribed": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertFalse(self.user.marketing_opt_in)
