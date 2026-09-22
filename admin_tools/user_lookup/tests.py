from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from finance.accounts.models import Account
from finance.transactions.Models.transacciones import Transaction
from support.audit.models import AuditLog


User = get_user_model()


class SupportUserLookupTests(APITestCase):
    support_reason = "Investigacion autorizada del ticket local"
    support_case = "LOCAL-001"

    def setUp(self):
        self.staff = User.objects.create_user(
            username="support-agent",
            email="support@example.com",
            password="test-password",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular-user",
            email="regular@example.com",
            password="test-password",
        )
        self.target = User.objects.create_user(
            username="target-user",
            email="target@example.com",
            first_name="Target",
            last_name="Person",
            password="test-password",
        )
        self.account = Account.objects.create(
            owner=self.target,
            name="Cuenta privada",
            initial_balance="1250000.00",
            balance="1250000.00",
        )
        Transaction.objects.create(
            owner=self.target,
            account=self.account,
            type=Transaction.Type.EXPENSE,
            amount="50000.00",
            date=date(2026, 9, 16),
            description="Descripcion financiera privada",
        )

    def _headers(self):
        return {
            "HTTP_X_SUPPORT_REASON": self.support_reason,
            "HTTP_X_SUPPORT_CASE": self.support_case,
        }

    def test_lookup_requires_authentication_and_staff_role(self):
        anonymous_response = self.client.get(
            "/api/internal/support/users/?q=target",
            **self._headers(),
        )
        self.assertIn(
            anonymous_response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )

        self.client.force_authenticate(self.regular_user)
        regular_response = self.client.get(
            "/api/internal/support/users/?q=target",
            **self._headers(),
        )
        self.assertEqual(regular_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_lookup_requires_an_explicit_support_reason(self):
        self.client.force_authenticate(self.staff)

        response = self.client.get("/api/internal/support/users/?q=target")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("support_reason", response.data)
        self.assertFalse(AuditLog.objects.exists())

    def test_lookup_rejects_oversized_search_and_case_metadata(self):
        self.client.force_authenticate(self.staff)

        oversized_query = self.client.get(
            f"/api/internal/support/users/?q={'x' * 256}",
            **self._headers(),
        )
        self.assertEqual(oversized_query.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("q", oversized_query.data)

        oversized_case = self.client.get(
            "/api/internal/support/users/?q=target",
            HTTP_X_SUPPORT_REASON=self.support_reason,
            HTTP_X_SUPPORT_CASE="x" * 101,
        )
        self.assertEqual(oversized_case.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("support_case", oversized_case.data)

    def test_search_is_limited_and_audited_without_raw_query(self):
        self.client.force_authenticate(self.staff)

        response = self.client.get(
            "/api/internal/support/users/?q=target@example.com",
            **self._headers(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.target.id)

        audit = AuditLog.objects.get(entity="UserSearch")
        self.assertEqual(audit.action, AuditLog.Action.READ)
        self.assertEqual(audit.user, self.staff)
        self.assertEqual(audit.metadata["support_case"], self.support_case)
        self.assertEqual(audit.metadata["actor_user_id"], self.staff.id)
        self.assertIn("query_hash", audit.metadata)
        self.assertNotIn("target@example.com", str(audit.metadata))

    def test_overview_returns_counts_without_financial_values_and_is_audited(self):
        self.client.force_authenticate(self.staff)

        response = self.client.get(
            f"/api/internal/support/users/{self.target.id}/",
            **self._headers(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["identity"]["id"], self.target.id)
        self.assertEqual(response.data["finance"]["accounts"]["total"], 1)
        self.assertEqual(response.data["finance"]["transactions"]["total"], 1)

        serialized = str(response.data)
        self.assertNotIn("1250000", serialized)
        self.assertNotIn("50000", serialized)
        self.assertNotIn("Descripcion financiera privada", serialized)

        audit = AuditLog.objects.get(entity="User", entity_id=str(self.target.id))
        self.assertEqual(audit.action, AuditLog.Action.READ)
        self.assertEqual(audit.user, self.target)
        self.assertEqual(audit.metadata["actor_user_id"], self.staff.id)
        self.assertEqual(audit.metadata["support_reason"], self.support_reason)
