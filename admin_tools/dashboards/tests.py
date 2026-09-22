from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from support.audit.models import AuditLog


User = get_user_model()


class OperationsDashboardTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="ops-staff", email="ops@example.com", password="secret123A", is_staff=True
        )
        self.user = User.objects.create_user(
            username="ops-user", email="ops-user@example.com", password="secret123A"
        )

    def test_dashboard_is_staff_only_and_audited(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/internal/support/operations/").status_code, 403)

        self.client.force_authenticate(self.staff)
        response = self.client.get("/api/internal/support/operations/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("outboxes", response.data)
        self.assertIn("scheduler", response.data)
        self.assertTrue(AuditLog.objects.filter(module="admin_tools.dashboards").exists())
