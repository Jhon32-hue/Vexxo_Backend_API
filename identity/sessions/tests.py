from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.sessions.services import register_user_session, revoke_user_session

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
