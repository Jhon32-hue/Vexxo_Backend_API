from datetime import date
from importlib import import_module
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from finance.accounts.models.account import AccountStatus


class CapabilityImportTests(SimpleTestCase):
    def setUp(self):
        self.user = get_user_model()(email="imports@example.test")

    def test_contact_limit_uses_canonical_contact_model(self):
        with (
            patch.object(self.user, "get_plan_config", return_value={"max_contacts": 1}),
            patch("contacts.models.Contact.objects.filter") as query,
        ):
            query.return_value.count.return_value = 1
            self.assertFalse(self.user.can_add_contact())
            query.assert_called_once_with(owner=self.user)

    def test_connected_limit_preserves_account_counting(self):
        with (
            patch.object(self.user, "get_plan_config", return_value={"max_connected_accounts": 2}),
            patch("finance.accounts.models.account.Account.objects.filter") as query,
        ):
            external = query.return_value.exclude.return_value.exclude.return_value
            external.count.return_value = 2
            self.assertFalse(self.user.can_add_api_connection())
            query.assert_called_once_with(
                owner=self.user, status__in=[AccountStatus.ACTIVE, AccountStatus.FROZEN]
            )
            query.return_value.exclude.assert_called_once_with(provider="")
            query.return_value.exclude.return_value.exclude.assert_called_once_with(external_id="")

    def test_monthly_limit_queries_current_model_across_year_boundary(self):
        with (
            patch.object(self.user, "get_plan_config", return_value={"max_monthly_reports": 1}),
            patch("reports.monthly_reports.models.MonthlyReportClose.objects.filter") as query,
        ):
            query.return_value.count.return_value = 1
            self.assertFalse(self.user.can_generate_monthly_report(date(2026, 12, 15)))
            query.assert_called_once_with(
                owner=self.user,
                created_at__gte=date(2026, 12, 1),
                created_at__lt=date(2027, 1, 1),
            )

    def test_monthly_limit_allows_remaining_capacity(self):
        with (
            patch.object(self.user, "get_plan_config", return_value={"max_monthly_reports": 2}),
            patch("reports.monthly_reports.models.MonthlyReportClose.objects.filter") as query,
        ):
            query.return_value.count.return_value = 1
            self.assertTrue(self.user.can_generate_monthly_report(date(2026, 11, 4)))

    def test_unlimited_report_plan_does_not_query_database(self):
        with (
            patch.object(self.user, "get_plan_config", return_value={"max_monthly_reports": None}),
            patch("reports.monthly_reports.models.MonthlyReportClose.objects.filter") as query,
        ):
            self.assertTrue(self.user.can_generate_monthly_report())
            query.assert_not_called()

    def test_report_query_error_is_not_converted_to_permission(self):
        with (
            patch.object(self.user, "get_plan_config", return_value={"max_monthly_reports": 1}),
            patch(
                "reports.monthly_reports.models.MonthlyReportClose.objects.filter",
                side_effect=RuntimeError("query unavailable"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "query unavailable"):
                self.user.can_generate_monthly_report()

    def test_reserved_realtime_modules_are_importable(self):
        for name in ("redis_channels", "routing", "typing", "unread_counters"):
            with self.subTest(module=name):
                module = import_module(f"realtime.{name}")
                self.assertIn("Reserved module", module.__doc__)
