import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from finance.accounts.models import AccountIntelligenceDispatchState
from finance.budgets.Models.shared_budget import SharedBudget
from social.teams.models import Membership, Team


User = get_user_model()


class MobileApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_sync_state_requires_authentication(self):
        response = self.client.get("/api/mobile/sync-state/")

        self.assertEqual(response.status_code, 401)

    def test_authenticated_user_can_read_sync_state(self):
        user = User.objects.create_user(
            username="mobile-sync-user",
            email="mobile-sync@example.com",
            password="VexxoPass2026!",
        )
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/mobile/sync-state/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["schema_version"], "mobile.sync_state.v1")
        self.assertIn("sections", response.data)
        self.assertIn("accounts", response.data["sections"])

    def test_bootstrap_is_read_only_when_projections_are_missing(self):
        user = User.objects.create_user(
            username="mobile-bootstrap-user",
            email="mobile-bootstrap@example.com",
            password="VexxoPass2026!",
        )
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/mobile/bootstrap/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["schema_version"], "mobile.bootstrap.v1")
        self.assertFalse(AccountIntelligenceDispatchState.objects.filter(owner=user).exists())

    def test_mobile_query_profiler_reports_bootstrap_queries(self):
        user = User.objects.create_user(
            username="mobile-query-profile-user",
            email="mobile-query-profile@example.com",
            password="VexxoPass2026!",
        )
        output = StringIO()

        call_command(
            "profile_mobile_queries",
            email=user.email,
            endpoint="bootstrap",
            stdout=output,
        )

        report = json.loads(output.getvalue())
        self.assertEqual(report["status_code"], 200)
        self.assertGreater(report["query_count"], 0)
        self.assertIn("repeated_query_groups", report)

    def test_mobile_query_benchmark_has_constant_query_growth(self):
        output = StringIO()

        call_command(
            "benchmark_mobile_queries",
            profiles="small,medium",
            top=0,
            max_query_growth=0,
            max_bootstrap_queries=100,
            max_cached_bootstrap_queries=25,
            max_sync_state_queries=25,
            stdout=output,
        )

        report = json.loads(output.getvalue())
        self.assertEqual(report["growth"]["bootstrap"]["query_delta"], 0)
        self.assertEqual(report["growth"]["bootstrap-cached"]["query_delta"], 0)
        self.assertEqual(report["growth"]["sync-state"]["query_delta"], 0)
        self.assertFalse(User.objects.filter(email__startswith="mobile-perf-").exists())

    def test_bootstrap_uses_sync_state_versions_and_skips_unchanged_payloads(self):
        user = User.objects.create_user(
            username="mobile-incremental-user",
            email="mobile-incremental@example.com",
            password="VexxoPass2026!",
        )
        self.client.force_authenticate(user=user)

        sync_state = self.client.get("/api/mobile/sync-state/")
        server_versions = {
            key: section["version"]
            for key, section in sync_state.data["sections"].items()
        }
        bootstrap = self.client.get(
            "/api/mobile/bootstrap/",
            HTTP_X_VEXXO_MOBILE_SECTION_VERSIONS=json.dumps(server_versions),
        )

        self.assertEqual(bootstrap.status_code, 200, bootstrap.data)
        self.assertEqual(bootstrap.data["meta"]["section_versions"], server_versions)
        self.assertTrue(all(section["unchanged"] for section in bootstrap.data["sections"].values()))
        self.assertTrue(all(section["data"] is None for section in bootstrap.data["sections"].values()))

    def test_bootstrap_builds_only_sections_with_stale_versions(self):
        user = User.objects.create_user(
            username="mobile-partial-user",
            email="mobile-partial@example.com",
            password="VexxoPass2026!",
        )
        self.client.force_authenticate(user=user)
        sync_state = self.client.get("/api/mobile/sync-state/")
        server_versions = {
            key: section["version"]
            for key, section in sync_state.data["sections"].items()
        }
        server_versions["dashboard"] = "stale-dashboard-version"

        bootstrap = self.client.get(
            "/api/mobile/bootstrap/",
            HTTP_X_VEXXO_MOBILE_SECTION_VERSIONS=json.dumps(server_versions),
        )

        self.assertFalse(bootstrap.data["sections"]["dashboard"]["unchanged"])
        self.assertIsInstance(bootstrap.data["sections"]["dashboard"]["data"], dict)
        for key, section in bootstrap.data["sections"].items():
            if key == "dashboard":
                continue
            self.assertTrue(section["unchanged"], key)
            self.assertIsNone(section["data"], key)

    def test_markets_uses_the_mobile_market_builder(self):
        user = User.objects.create_user(
            username="mobile-markets-user",
            email="mobile-markets@example.com",
            password="VexxoPass2026!",
        )
        self.client.force_authenticate(user=user)

        with patch("api.mobile.views.build_mobile_market_snapshot", return_value={"base_currency": "COP"}):
            response = self.client.get("/api/mobile/markets/?base=COP")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["data"]["base_currency"], "COP")

    def test_shared_budget_membership_is_included_in_sync_state_and_bootstrap(self):
        owner = User.objects.create_user(
            username="mobile-budget-owner",
            email="mobile-budget-owner@example.com",
            password="VexxoPass2026!",
        )
        member = User.objects.create_user(
            username="mobile-budget-member",
            email="mobile-budget-member@example.com",
            password="VexxoPass2026!",
        )
        team = Team.objects.create(owner=owner, name="Equipo mobile", is_personal=False)
        Membership.objects.create(team=team, user=member, role="viewer", is_active=True)
        budget = SharedBudget.objects.create(
            owner=owner,
            team=team,
            name="Viaje compartido",
            month="2026-09",
            amount="500000.00",
        )
        self.client.force_authenticate(user=member)

        sync_state = self.client.get("/api/mobile/sync-state/")
        bootstrap = self.client.get("/api/mobile/bootstrap/")

        self.assertEqual(sync_state.status_code, 200)
        self.assertEqual(sync_state.data["sections"]["shared_budgets"]["signature"]["count"], 1)
        self.assertEqual(bootstrap.status_code, 200)
        result_ids = {
            row["id"] for row in bootstrap.data["sections"]["shared_budgets"]["data"]["results"]
        }
        self.assertIn(budget.pk, result_ids)
