from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from finance.accounts.models import Account
from finance.transactions.Models import Transaction
from reports.monthly_reports.models import MonthlyReportClose
from reports.monthly_reports.services import close_monthly_report


class MonthlyReportCloseTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="monthly-close-owner",
            email="monthly-close@example.com",
            password="TestPass2026!",
        )
        cop = Account.objects.create(owner=self.user, name="COP account", currency="COP")
        usd = Account.objects.create(owner=self.user, name="USD account", currency="USD")
        Transaction.objects.create(owner=self.user, account=cop, type="income", amount="120.00", date=date(2026, 8, 1))
        Transaction.objects.create(owner=self.user, account=cop, type="expense", amount="20.00", date=date(2026, 8, 2))
        Transaction.objects.create(owner=self.user, account=usd, type="income", amount="999.00", date=date(2026, 8, 3))

    def test_close_is_idempotent_and_currency_scoped(self):
        close, created = close_monthly_report(
            owner=self.user,
            month="2026-08",
            currency="COP",
            timezone_name="America/Bogota",
        )
        repeated, repeated_created = close_monthly_report(
            owner=self.user,
            month="2026-08",
            currency="COP",
            timezone_name="America/Bogota",
        )
        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(repeated.pk, close.pk)
        self.assertEqual(close.snapshot.payload["data"]["net"], "100.00")
        self.assertEqual(close.snapshot.payload["data"]["transaction_count"], 2)

    def test_regeneration_requires_reason_and_preserves_versions(self):
        first, _ = close_monthly_report(
            owner=self.user,
            month="2026-08",
            currency="COP",
            timezone_name="America/Bogota",
        )
        with self.assertRaises(ValidationError):
            close_monthly_report(
                owner=self.user,
                month="2026-08",
                currency="COP",
                timezone_name="America/Bogota",
                regenerate=True,
                reason="short",
            )
        second, created = close_monthly_report(
            owner=self.user,
            month="2026-08",
            currency="COP",
            timezone_name="America/Bogota",
            regenerate=True,
            reason="Correction approved by finance support",
        )
        first.refresh_from_db()
        self.assertTrue(created)
        self.assertFalse(first.is_current)
        self.assertEqual(first.status, MonthlyReportClose.Status.SUPERSEDED)
        self.assertEqual(second.version, 2)
        self.assertEqual(second.supersedes_id, first.pk)
        self.assertEqual(second.snapshot.supersedes_id, first.snapshot_id)
