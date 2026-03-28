from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.devices.services import register_or_update_device, trust_device

User = get_user_model()


class UserDeviceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="device-user", email="device@example.com", password="TestPass2026!")

    def test_register_or_update_device_creates_record(self):
        device = register_or_update_device(
            user=self.user,
            payload={"fingerprint": "fp-123", "device_type": "mobile", "platform": "android"},
        )
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.fingerprint, "fp-123")

    def test_trust_device_updates_trust_level(self):
        device = register_or_update_device(user=self.user, payload={"fingerprint": "fp-456"})
        trust_device(device)
        device.refresh_from_db()
        self.assertEqual(device.trust_level, "trusted")
