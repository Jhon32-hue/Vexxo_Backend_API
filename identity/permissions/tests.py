from django.contrib.auth import get_user_model
from django.test import TestCase

from identity.permissions.services import grant_permission, revoke_permission

User = get_user_model()


class UserPermissionGrantTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin-user", email="admin@example.com", password="TestPass2026!")
        self.target = User.objects.create_user(username="target-user", email="target@example.com", password="TestPass2026!")

    def test_grant_permission_creates_granted_record(self):
        grant = grant_permission(
            user=self.target,
            granted_by=self.admin,
            data={"permission_code": "accounts.export", "scope_type": "global", "scope_id": "", "source": "admin"},
        )
        self.assertEqual(grant.status, "granted")
        self.assertEqual(grant.permission_code, "accounts.export")

    def test_revoke_permission_marks_revoked(self):
        grant = grant_permission(
            user=self.target,
            granted_by=self.admin,
            data={"permission_code": "reports.generate", "scope_type": "global", "scope_id": "", "source": "admin"},
        )
        revoke_permission(grant, reason="support_request")
        grant.refresh_from_db()
        self.assertEqual(grant.status, "revoked")
