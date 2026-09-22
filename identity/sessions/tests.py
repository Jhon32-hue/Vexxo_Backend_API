from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import AccessToken

from identity.sessions.authentication import SessionBoundJWTAuthentication
from identity.sessions.services import register_user_session, revoke_user_session
from identity.devices.models import UserDevice
from identity.devices.services import revoke_device
from identity.sessions.models import SessionRiskLevel

User = get_user_model()


class UserSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="session-user", email="session@example.com", password="TestPass2026!")

    def test_register_user_session_creates_active_session(self):
        session = register_user_session(user=self.user, session_key="sess-1")
        self.assertEqual(session.status, "active")
        self.assertEqual(session.session_key, "sess-1")

    def test_revoke_user_session_marks_revoked(self):
        session = register_user_session(user=self.user, session_key="sess-2")
        revoke_user_session(session, reason="manual")
        session.refresh_from_db()
        self.assertEqual(session.status, "revoked")

    def test_revoking_device_invalidates_its_session_immediately(self):
        device = UserDevice.objects.create(user=self.user, fingerprint="session-device")
        session = register_user_session(user=self.user, session_key="sess-device", device=device)
        revoke_device(device)
        session.refresh_from_db()
        self.assertEqual(session.status, "revoked")
        self.assertEqual(session.revocation_reason, "device_revoked")

    def test_critical_risk_session_is_revoked_during_authentication(self):
        token = AccessToken.for_user(self.user)
        session = register_user_session(
            user=self.user,
            session_key="sess-critical",
            access_jti=str(token["jti"]),
        )
        session.risk_level = SessionRiskLevel.CRITICAL
        session.save(update_fields=["risk_level", "updated_at"])
        request = APIRequestFactory().get(
            "/api/identity/sessions/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        with self.assertRaises(AuthenticationFailed):
            SessionBoundJWTAuthentication().authenticate(request)

        session.refresh_from_db()
        self.assertEqual(session.status, "revoked")
        self.assertEqual(session.revocation_reason, "critical_risk")
