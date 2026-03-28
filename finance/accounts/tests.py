"""
Pruebas basicas del modulo accounts.

Descripcion general:
- cubre guardas de plan y contratos de eventos del dominio

Analisis detallado:
- no reemplaza pruebas integrales de API, pero protege invariantes clave del
  modulo mientras sigue creciendo
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from finance.accounts.domain.events import (
    build_account_balance_payload,
    build_account_lifecycle_payload,
    build_account_sync_payload,
    get_account_event_catalog,
    get_account_event_governance,
    get_account_event_runtime,
)
from finance.accounts.domain.guards import get_account_plan_snapshot, primary_account_limit_errors
from finance.accounts.models import (
    Account,
    AccountMembership,
    AccountOwnerMetrics,
    AccountPortfolioSnapshot,
    AccountProductSignal,
    AccountRiskSnapshot,
    AccountStatus,
    AccountType,
)
from finance.accounts.services.intelligence_service import refresh_account_intelligence_for_user
from finance.accounts.services.snapshot_policy_service import get_balance_snapshot_policy_summary

User = get_user_model()


class AccountDomainGuardsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="guard-user",
            email="guard@example.com",
            password="secret123",
            plan="free",
        )

    def test_plan_snapshot_counts_active_accounts(self):
        Account.objects.create(owner=self.user, name="Cuenta 1", currency="COP")
        Account.objects.create(owner=self.user, name="Cuenta 2", currency="USD")

        snapshot = get_account_plan_snapshot(self.user)

        self.assertEqual(snapshot["plan"], "free")
        self.assertEqual(snapshot["usage"]["active_accounts"], 2)
        self.assertEqual(snapshot["limits"]["max_active_accounts"], 3)

    def test_plan_snapshot_counts_frozen_accounts_against_plan(self):
        Account.objects.create(owner=self.user, name="Cuenta Activa", currency="COP", status=AccountStatus.ACTIVE)
        Account.objects.create(owner=self.user, name="Cuenta Frozen", currency="USD", status=AccountStatus.FROZEN)

        snapshot = get_account_plan_snapshot(self.user)

        self.assertEqual(snapshot["usage"]["active_accounts"], 2)
        self.assertIn(AccountStatus.FROZEN, snapshot["usage"]["counted_statuses"])

    def test_primary_limit_errors_for_free_plan(self):
        Account.objects.create(owner=self.user, name="Principal", currency="COP", is_primary=True)

        errors = primary_account_limit_errors(self.user)

        self.assertIn("is_primary", errors)
        self.assertEqual(errors["is_primary"]["limit"], 1)


class AccountDomainEventsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="events-user",
            email="events@example.com",
            password="secret123",
            plan="plus",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Broker",
            type=AccountType.BROKERAGE,
            currency="USD",
            provider="binance",
            external_id="acc-ext-1",
            status=AccountStatus.ACTIVE,
        )

    def test_build_account_balance_payload(self):
        payload = build_account_balance_payload(
            account=self.account,
            old_balance=Decimal("10.00"),
            new_balance=Decimal("15.50"),
            reason="manual_recalc",
            transaction_id=99,
        )

        self.assertEqual(payload["account_id"], str(self.account.pk))
        self.assertEqual(payload["delta"], "5.50")
        self.assertEqual(payload["transaction_id"], "99")

    def test_build_account_sync_payload(self):
        payload = build_account_sync_payload(
            account=self.account,
            change="schedule_sync",
            extra={"worker": "sync-service"},
        )

        self.assertEqual(payload["account_id"], str(self.account.pk))
        self.assertEqual(payload["change"], "schedule_sync")
        self.assertTrue(payload["has_external_link"])
        self.assertEqual(payload["worker"], "sync-service")
        self.assertEqual(payload["institution"], self.account.institution)

    def test_build_account_lifecycle_payload(self):
        payload = build_account_lifecycle_payload(
            account=self.account,
            change="updated",
            before={"name": "Old"},
            after={"name": "Broker"},
        )

        self.assertEqual(payload["change"], "updated")
        self.assertEqual(payload["before"]["name"], "Old")
        self.assertEqual(payload["after"]["name"], "Broker")
        self.assertEqual(payload["owner_id"], str(self.user.pk))

    def test_event_catalog_declares_balance_listener(self):
        catalog = get_account_event_catalog()
        balance_event = next(item for item in catalog if item["event_type"] == "accounts.balance.updated.v1")

        self.assertIn("alerts.handle_account_balance_updated", balance_event["current_local_listeners"])

    def test_event_runtime_declares_outbox_pipeline(self):
        runtime = get_account_event_runtime()

        self.assertEqual(runtime["aggregate_type"], "account")
        self.assertIn("finance.accounts.models.outbox.DomainEventOutbox", runtime["transport_today"])
        self.assertIn("dispatcher opcional common.gcp.pubsub_dispatcher", runtime["transport_today"])

    def test_event_catalog_declares_granular_sync_failed_event(self):
        catalog = get_account_event_catalog()
        sync_failed_event = next(item for item in catalog if item["event_type"] == "accounts.sync.failed.v1")

        self.assertIn("alerts.handle_account_sync_failed", sync_failed_event["current_local_listeners"])

    def test_event_catalog_includes_governance_metadata(self):
        catalog = get_account_event_catalog()
        created_event = next(item for item in catalog if item["event_type"] == "accounts.created.v1")

        self.assertEqual(created_event["contract_status"], "active")
        self.assertEqual(created_event["schema_version"], "v1")
        self.assertIn("account_id", created_event["payload_fields"])

    def test_event_governance_registry_exposes_versioning_policy(self):
        governance = get_account_event_governance()

        self.assertEqual(governance["schema_registry_style"], "lightweight_inline_registry")
        self.assertEqual(governance["versioning_policy"]["breaking_changes"], "create_new_version")
        self.assertIn("accounts.balance.updated.v1", governance["registry"])


class AccountAggregateHelpersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="aggregate-user",
            email="aggregate@example.com",
            password="secret123",
            plan="free",
        )
        self.account = Account.objects.create(owner=self.user, name="Caja", currency="COP")

    def test_ensure_owner_membership_creates_canonical_owner_membership(self):
        membership = self.account.ensure_owner_membership()

        self.assertIsInstance(membership, AccountMembership)
        self.assertEqual(membership.account_id, self.account.id)
        self.assertEqual(membership.user_id, self.user.id)
        self.assertTrue(membership.is_active)
        self.assertTrue(membership.can_manage_account_settings)


class AccountIntelligenceProjectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="intelligence-user",
            email="intelligence@example.com",
            password="secret123",
            plan="plus",
        )
        self.primary = Account.objects.create(
            owner=self.user,
            name="Banco Principal",
            currency="COP",
            type=AccountType.BANK,
            balance=Decimal("1500.00"),
            virtual_balance_base=Decimal("1500.00"),
            base_currency="COP",
            is_primary=True,
            provider="bancolombia",
            external_id="bank-1",
        )
        self.primary.mark_sync_ok()
        self.primary.ensure_owner_membership()

        self.investment = Account.objects.create(
            owner=self.user,
            name="Broker USD",
            currency="USD",
            type=AccountType.BROKERAGE,
            ownership="shared",
            balance=Decimal("800.00"),
            virtual_balance_base=Decimal("3200000.00"),
            base_currency="COP",
            goal_amount=Decimal("1000.00"),
            status=AccountStatus.FROZEN,
        )
        self.investment.ensure_owner_membership()

    def test_refresh_account_intelligence_creates_snapshots_and_metrics(self):
        result = refresh_account_intelligence_for_user(self.user)

        portfolio = result["portfolio_snapshot"]
        risk = result["risk_snapshot"]

        self.assertIsInstance(portfolio, AccountPortfolioSnapshot)
        self.assertIsInstance(risk, AccountRiskSnapshot)
        self.assertEqual(portfolio.total_accounts, 2)
        self.assertEqual(portfolio.currencies_count, 2)
        self.assertTrue(portfolio.has_multi_currency_accounts)
        self.assertTrue(portfolio.has_investment_exposure)
        self.assertTrue(portfolio.has_shared_financial_behavior)

        owner_metrics = AccountOwnerMetrics.objects.get(owner=self.user)
        self.assertEqual(owner_metrics.total_accounts, 2)
        self.assertEqual(owner_metrics.external_accounts, 1)

    def test_refresh_account_intelligence_generates_product_signals(self):
        refresh_account_intelligence_for_user(self.user)

        signal_codes = set(
            AccountProductSignal.objects.filter(owner=self.user, is_active=True).values_list("signal_code", flat=True)
        )

        self.assertIn("likely_international_user", signal_codes)
        self.assertIn("high_shared_finance_behavior", signal_codes)

    def test_account_health_properties_reflect_sync_and_membership_state(self):
        self.primary.last_consistent_snapshot_at = self.primary.updated_at
        self.primary.save(update_fields=["last_consistent_snapshot_at"])

        self.assertEqual(self.primary.integration_health, "recently_synced")
        self.assertEqual(self.primary.membership_health, "healthy")
        self.assertEqual(self.primary.balance_health, "healthy")


class AccountSnapshotPolicyTests(TestCase):
    def test_snapshot_policy_summary_exposes_retention_configuration(self):
        policy = get_balance_snapshot_policy_summary()

        self.assertEqual(policy["scheduled_frequency"], "nightly")
        self.assertGreaterEqual(policy["retention_days"], 1)
        self.assertIn("scheduled_job", policy["sources"])
