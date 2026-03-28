from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.consents.services import grant_consent, revoke_consent

User = get_user_model()


class UserConsentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="consent-user", email="consent@example.com", password="TestPass2026!")

    def test_grant_consent_creates_granted_record(self):
        consent = grant_consent(
            user=self.user,
            data={"consent_type": "open_banking_data", "provider": "belvo", "scope_code": "balances.read"},
        )
        self.assertEqual(consent.status, "granted")
        self.assertEqual(consent.provider, "belvo")

    def test_revoke_consent_updates_status(self):
        consent = grant_consent(user=self.user, data={"consent_type": "marketing"})
        revoke_consent(consent, reason="user_request")
        consent.refresh_from_db()
        self.assertEqual(consent.status, "revoked")
