from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from identity.consents.dispatch_service import dispatch_consent_revocation_teardown
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

    @override_settings(
        IDENTITY_CONSENT_CLOUD_TASKS_ENABLED=False,
        ASYNC_EXECUTION_MODE_IDENTITY_CONSENTS="sync_inline_for_tests",
    )
    def test_dispatch_consent_revocation_uses_common_async_backend_inline_for_tests(self):
        result = dispatch_consent_revocation_teardown(
            user_id=self.user.pk,
            provider="belvo",
            consent_type="open_banking_data",
            event={"type": "users.consent.revoked.v1"},
        )

        self.assertEqual(result["result"], "inline_processed")
        self.assertEqual(result["dispatch_backend"], "sync_inline_for_tests")
        self.assertIn("disabled_accounts", result)

    @override_settings(
        IDENTITY_CONSENT_CLOUD_TASKS_ENABLED=False,
        ASYNC_EXECUTION_MODE_IDENTITY_CONSENTS="disabled",
    )
    def test_dispatch_consent_revocation_can_fail_closed_when_pipeline_disabled(self):
        result = dispatch_consent_revocation_teardown(
            user_id=self.user.pk,
            provider="belvo",
            consent_type="open_banking_data",
            event={"type": "users.consent.revoked.v1"},
        )

        self.assertEqual(result["result"], "pipeline_unavailable")
