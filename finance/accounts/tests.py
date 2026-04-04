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
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from common.domain_events import EventContext, EventNames, VexxoAppDomainEvent
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
    AccountAccess,
    AccountBalanceFallback,
    AccountIntelligenceDispatchState,
    AccountInvitation,
    AccountMembership,
    AccountOwnerMetrics,
    AccountPortfolioSnapshot,
    AccountProductSignal,
    AccountRiskSnapshot,
    AccountStatus,
    AccountType,
)
from finance.accounts.event_handlers import handle_user_permission_revoked
from finance.accounts.services.account_access_migration_service import migrate_account_access_entry
from finance.accounts.services.account_balance_fallback_service import record_account_balance_fallback
from finance.accounts.services.account_invitation_service import issue_membership_invitation
from finance.accounts.services.event_service import publish_outbox_event
from finance.accounts.services.intelligence_dispatch_service import dispatch_account_intelligence_refresh
from finance.accounts.services.intelligence_dispatch_service import report_account_intelligence_worker_status
from finance.accounts.services.account_sync_service import (
    mark_account_sync_error,
    mark_account_sync_running,
    mark_account_sync_success,
    schedule_account_sync,
)
from finance.accounts.services.intelligence_service import refresh_account_intelligence_for_user
from finance.accounts.services.outbox_service import publish_account_event
from finance.accounts.services.permission_service import user_can_post_transactions
from finance.accounts.services.snapshot_policy_service import get_balance_snapshot_policy_summary
from finance.accounts.services.user_integration_service import ensure_user_financial_home
from finance.accounts.use_cases import apply_account_balance_deltas
from finance.accounts.views import AccountBalanceFallbackViewSet, AccountPortfolioSnapshotViewSet

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
        self.assertIn("management command / worker accounts_publish_outbox -> publish_outbox_event", runtime["transport_today"])
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


class AccountInvitationLifecycleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner-invite",
            email="owner-invite@example.com",
            password="secret123",
            plan="plus",
        )
        self.member = User.objects.create_user(
            username="member-invite",
            email="member-invite@example.com",
            password="secret123",
            plan="free",
        )
        self.account = Account.objects.create(owner=self.owner, name="Compartida", currency="COP")
        self.account.ensure_owner_membership()
        self.membership = AccountMembership.objects.create(
            account=self.account,
            user=self.member,
            role="member",
            access_mode="full",
            invited_by=self.owner,
            is_active=False,
        )

    def test_issue_membership_invitation_creates_versioned_invitation(self):
        invitation = issue_membership_invitation(membership=self.membership, invited_by=self.owner)
        self.membership.refresh_from_db()

        self.assertIsInstance(invitation, AccountInvitation)
        self.assertEqual(invitation.membership_id, self.membership.id)
        self.assertEqual(invitation.status, AccountInvitation.Status.PENDING)
        self.assertTrue(invitation.is_current)
        self.assertEqual(self.membership.invitation_token, invitation.token)
        self.assertTrue(self.membership.invitation_pending)

    def test_accept_membership_marks_invitation_accepted(self):
        invitation = issue_membership_invitation(membership=self.membership, invited_by=self.owner)
        self.membership.accept()
        invitation.refresh_from_db()
        self.membership.refresh_from_db()

        self.assertEqual(invitation.status, AccountInvitation.Status.ACCEPTED)
        self.assertFalse(invitation.is_current)
        self.assertTrue(self.membership.is_active)
        self.assertIsNotNone(self.membership.accepted_at)

    def test_accept_with_commit_false_keeps_changes_in_memory(self):
        invitation = issue_membership_invitation(membership=self.membership, invited_by=self.owner)

        self.membership.accept(commit=False)
        invitation.refresh_from_db()
        persisted = AccountMembership.objects.get(pk=self.membership.pk)

        self.assertEqual(invitation.status, AccountInvitation.Status.PENDING)
        self.assertFalse(persisted.is_active)
        self.assertTrue(self.membership.is_active)


class AccountBalanceFallbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fallback-user",
            email="fallback@example.com",
            password="secret123",
            plan="plus",
        )
        self.account = Account.objects.create(owner=self.user, name="Cuenta fallback", currency="COP", balance="10.00")

    def test_record_balance_fallback_persists_delta_and_context(self):
        event = record_account_balance_fallback(
            account=self.account,
            transaction_id="tx-1",
            reason="tx_fallback_recalc",
            old_state_present=False,
            affected_account_ids=[str(self.account.pk)],
            old_balance="10.00",
            new_balance="12.50",
            recalculated=True,
            metadata={"source": "test"},
        )

        self.assertIsInstance(event, AccountBalanceFallback)
        self.assertEqual(str(event.delta), "2.500000")
        self.assertTrue(event.recalculated)
        self.assertEqual(event.metadata["source"], "test")


class AccountBalanceFallbackViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="fallback-view-user",
            email="fallback-view@example.com",
            password="secret123",
            plan="plus",
        )
        self.account = Account.objects.create(owner=self.user, name="Cuenta visible", currency="COP", balance="20.00")
        record_account_balance_fallback(
            account=self.account,
            transaction_id="tx-visible-1",
            reason="tx_fallback_recalc",
            old_state_present=False,
            affected_account_ids=[str(self.account.pk)],
            old_balance="20.00",
            new_balance="22.00",
            recalculated=True,
            metadata={"source": "signals"},
        )
        record_account_balance_fallback(
            account=self.account,
            transaction_id="tx-visible-2",
            reason="tx_fallback_recalc",
            old_state_present=True,
            affected_account_ids=[str(self.account.pk)],
            old_balance="22.00",
            new_balance="22.00",
            recalculated=False,
            metadata={"source": "signals"},
        )

    def test_fallback_view_list_filters_by_scope(self):
        view = AccountBalanceFallbackViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/finance/accounts/fallbacks-balance-cuenta/?recalculated=true")
        force_authenticate(request, user=self.user)
        response = view(request)
        rows = response.data if isinstance(response.data, list) else response.data.get("results", [])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["transaction_id"], "tx-visible-1")

    def test_fallback_view_health_aggregates_reason_counts(self):
        view = AccountBalanceFallbackViewSet.as_view({"get": "health"})
        request = self.factory.get("/api/finance/accounts/fallbacks-balance-cuenta/health/")
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_fallbacks"], 2)
        self.assertEqual(response.data["by_reason"][0]["reason"], "tx_fallback_recalc")


class AccountOutboxAsyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="outbox-user",
            email="outbox@example.com",
            password="secret123",
            plan="plus",
        )
        self.account = Account.objects.create(owner=self.user, name="Outbox", currency="COP")

    def test_publish_account_event_leaves_pending_outbox_for_worker(self):
        event = publish_account_event(
            account=self.account,
            event_type="accounts.updated.v1",
            payload=build_account_lifecycle_payload(account=self.account, change="updated"),
            metadata={"correlation_id": "corr-1", "request_id": "req-1"},
        )
        event.refresh_from_db()

        self.assertEqual(event.status, "pending")
        self.assertIsNone(event.published_at)
        self.assertEqual(event.correlation_id, "corr-1")
        self.assertEqual(event.request_id, "req-1")

    def test_publish_outbox_event_skips_local_phase_after_external_failure(self):
        event = publish_account_event(
            account=self.account,
            event_type="accounts.updated.v1",
            payload=build_account_lifecycle_payload(account=self.account, change="updated"),
        )

        calls: list[tuple[bool, bool]] = []

        def fail_external(*args, **kwargs):
            calls.append((kwargs.get("include_local", True), kwargs.get("include_external", True)))
            if kwargs.get("include_external"):
                raise RuntimeError("pubsub_down")
            return object()

        with patch("finance.accounts.services.event_service.publish_domain_event", side_effect=fail_external):
            publish_outbox_event(event, publisher="worker-test")

        event.refresh_from_db()
        self.assertEqual(calls, [(True, False), (False, True)])
        self.assertEqual(event.status, "failed")
        self.assertEqual(event.metadata["_vexxo_delivery"]["local"]["result"], "success")
        self.assertNotIn("external", {key: value["result"] for key, value in event.metadata["_vexxo_delivery"].items() if value})

        calls.clear()
        with patch(
            "finance.accounts.services.event_service.publish_domain_event",
            side_effect=lambda *args, **kwargs: calls.append(
                (kwargs.get("include_local", True), kwargs.get("include_external", True))
            ) or object(),
        ):
            publish_outbox_event(event, publisher="worker-test")

        event.refresh_from_db()
        self.assertEqual(calls, [(False, True)])
        self.assertEqual(event.status, "published")

    def test_publish_outbox_command_retries_failed_rows_below_max_retries(self):
        event = publish_account_event(
            account=self.account,
            event_type="accounts.updated.v1",
            payload=build_account_lifecycle_payload(account=self.account, change="updated"),
        )
        event.mark_failed("temporary_error")

        stdout = StringIO()
        call_command(
            "accounts_publish_outbox",
            batch_size=10,
            max_retries=3,
            retry_cooldown_seconds=0,
            dry_run=True,
            stdout=stdout,
        )

        self.assertIn("[outbox] batch=1", stdout.getvalue())

    @override_settings(
        ACCOUNTS_OUTBOX_MAX_RETRIES=3,
        ACCOUNTS_OUTBOX_RETRY_BASE_SECONDS=10,
        ACCOUNTS_OUTBOX_RETRY_BACKOFF_FACTOR=2,
        ACCOUNTS_OUTBOX_RETRY_MAX_SECONDS=60,
    )
    def test_publish_outbox_event_schedules_backoff_and_dead_letter(self):
        event = publish_account_event(
            account=self.account,
            event_type="accounts.updated.v1",
            payload=build_account_lifecycle_payload(account=self.account, change="updated"),
        )

        with patch("finance.accounts.services.event_service.publish_domain_event", side_effect=RuntimeError("pubsub_down")):
            publish_outbox_event(event, publisher="worker-test")
        event.refresh_from_db()

        self.assertEqual(event.status, "failed")
        self.assertEqual(event.retry_count, 1)
        self.assertEqual(event.last_backoff_seconds, 10)
        self.assertIsNotNone(event.next_attempt_at)
        self.assertIsNone(event.dead_lettered_at)

        with patch("finance.accounts.services.event_service.publish_domain_event", side_effect=RuntimeError("pubsub_down")):
            publish_outbox_event(event, publisher="worker-test")
        event.refresh_from_db()
        self.assertEqual(event.last_backoff_seconds, 20)
        self.assertEqual(event.status, "failed")

        with patch("finance.accounts.services.event_service.publish_domain_event", side_effect=RuntimeError("pubsub_down")):
            publish_outbox_event(event, publisher="worker-test")
        event.refresh_from_db()

        self.assertEqual(event.status, "dead_letter")
        self.assertIsNotNone(event.dead_lettered_at)
        self.assertIn("retries_exhausted=3", event.dead_letter_reason)


class AccountSyncRuntimeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sync-runtime-user",
            email="sync-runtime@example.com",
            password="secret123",
            plan="plus",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Sync",
            currency="COP",
            provider="plaid",
            external_id="ext-1",
        )

    def test_schedule_and_running_reuse_same_sync_run_id(self):
        schedule_account_sync(account=self.account, data={})
        self.account.refresh_from_db()
        scheduled_run_id = self.account.sync_runtime["current_run_id"]

        mark_account_sync_running(account=self.account, data={})
        self.account.refresh_from_db()

        self.assertEqual(self.account.sync_status, "running")
        self.assertEqual(self.account.sync_runtime["current_run_id"], scheduled_run_id)
        self.assertEqual(self.account.sync_runtime["current_phase"], "running")

    def test_terminal_transition_ignores_stale_run_and_keeps_monotonic_state(self):
        mark_account_sync_running(account=self.account, data={"sync_run_id": "run-a"})
        self.account.refresh_from_db()

        mark_account_sync_success(account=self.account, data={"sync_run_id": "run-b", "duration_ms": 10})
        self.account.refresh_from_db()
        self.assertEqual(self.account.sync_status, "running")
        self.assertEqual(self.account.sync_runtime["current_run_id"], "run-a")
        self.assertEqual(self.account.sync_runtime["last_transition_result"], "stale_run")

        mark_account_sync_success(account=self.account, data={"sync_run_id": "run-a", "duration_ms": 10})
        self.account.refresh_from_db()
        self.assertEqual(self.account.sync_status, "ok")
        self.assertEqual(self.account.sync_runtime["last_terminal_run_id"], "run-a")
        self.assertEqual(self.account.sync_runtime["current_run_id"], "")

        mark_account_sync_error(account=self.account, data={"sync_run_id": "run-a", "message": "late"})
        self.account.refresh_from_db()
        self.assertEqual(self.account.sync_status, "ok")
        self.assertEqual(self.account.sync_runtime["last_transition_result"], "already_terminal")


class AccountAccessMigrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner-access",
            email="owner-access@example.com",
            password="secret123",
            plan="plus",
        )
        self.viewer = User.objects.create_user(
            username="viewer-access",
            email="viewer-access@example.com",
            password="secret123",
            plan="free",
        )
        self.account = Account.objects.create(owner=self.owner, name="Legacy Shared", currency="COP")

    @override_settings(ACCOUNTS_ACCOUNT_ACCESS_LEGACY_WRITES_ENABLED=True)
    def test_migrate_account_access_entry_creates_membership(self):
        access = AccountAccess.objects.create(
            account=self.account,
            user=self.viewer,
            role="viewer",
            can_spend=False,
            can_view_balance=True,
            can_view_transactions=True,
            invited_by=self.owner,
            is_active=True,
        )

        membership = migrate_account_access_entry(access=access, deactivate_legacy=True)
        access.refresh_from_db()

        self.assertEqual(membership.account_id, self.account.id)
        self.assertEqual(membership.user_id, self.viewer.id)
        self.assertEqual(membership.role, "viewer")
        self.assertEqual(membership.access_mode, "read_only")
        self.assertFalse(access.is_active)

    def test_account_access_new_writes_are_blocked_by_default(self):
        with self.assertRaises(ValidationError):
            AccountAccess.objects.create(
                account=self.account,
                user=self.viewer,
                role="viewer",
            )


class AccountLegacyRetirementTests(TestCase):
    def test_owner_read_only_flag_no_longer_blocks_operations(self):
        user = User.objects.create_user(
            username="legacy-retired-user",
            email="legacy-retired@example.com",
            password="secret123",
            plan="plus",
        )
        account = Account.objects.create(owner=user, name="Legacy Flag", currency="COP", balance="10.00", read_only=True)

        self.assertTrue(user_can_post_transactions(user, account))

        apply_account_balance_deltas(
            deltas={account.pk: Decimal("5.00")},
            reason="legacy_retirement_test",
            publish_bus_after_commit=False,
        )
        account.refresh_from_db()

        self.assertEqual(str(account.balance), "15.00")


class AccountIdentityIntegrationHardeningTests(TestCase):
    def test_ensure_user_financial_home_is_idempotent_on_currency_change(self):
        user = User.objects.create_user(
            username="idempotent-home",
            email="idempotent-home@example.com",
            password="secret123",
            plan="free",
            preferred_currency="COP",
        )

        first = ensure_user_financial_home(user)
        user.preferred_currency = "USD"
        user.save(update_fields=["preferred_currency"])
        second = ensure_user_financial_home(user)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Account.objects.filter(owner=user).count(), 1)

    def test_permission_revoked_cuts_provider_integration_access(self):
        user = User.objects.create_user(
            username="permission-revoke-user",
            email="permission-revoke@example.com",
            password="secret123",
            plan="plus",
        )
        account = Account.objects.create(
            owner=user,
            name="Cuenta API",
            currency="COP",
            provider="belvo",
            external_id="ext-99",
            allow_auto_sync=True,
            sync_cursor="cursor-1",
            provider_metadata={"existing": True},
        )

        event = VexxoAppDomainEvent(
            type=EventNames.USER_PERMISSION_REVOKED,
            context=EventContext.IDENTITY,
            payload={
                "user_id": str(user.pk),
                "permission_code": "consents.open_banking_data.enabled",
                "scope_id": "open_banking_data:belvo:balances.read",
            },
        )
        handle_user_permission_revoked(event)
        account.refresh_from_db()

        self.assertFalse(account.allow_auto_sync)
        self.assertEqual(account.sync_cursor, "")
        self.assertEqual(account.provider_metadata["integration_access"], "revoked")
        self.assertEqual(account.provider_metadata["integration_revoked_reason"], "permission_revoked")


class AccountIntelligenceDispatchHardeningTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="intelligence-dispatch-user",
            email="intelligence-dispatch@example.com",
            password="secret123",
            plan="plus",
        )

    @override_settings(ACCOUNTS_INTELLIGENCE_LOCAL_FALLBACK_ENABLED=True)
    def test_dispatch_refresh_coalesces_repeated_requests(self):
        with patch("finance.accounts.services.intelligence_service.refresh_account_intelligence_for_user") as refresh_mock:
            first = dispatch_account_intelligence_refresh(owner_id=self.user.pk, source="test.coalesce")
            second = dispatch_account_intelligence_refresh(owner_id=self.user.pk, source="test.coalesce")

        state = AccountIntelligenceDispatchState.objects.get(owner=self.user)

        self.assertEqual(first["result"], "local_fallback")
        self.assertEqual(second["result"], "coalesced")
        self.assertEqual(refresh_mock.call_count, 1)
        self.assertFalse(state.pending_request)
        self.assertEqual(state.request_count, 2)

    def test_report_worker_status_tracks_started_and_completed(self):
        state = AccountIntelligenceDispatchState.objects.create(
            owner=self.user,
            pending_request=True,
            last_task_name="task-1",
            last_result="enqueued",
        )

        started = report_account_intelligence_worker_status(
            owner_id=self.user.pk,
            status="started",
            task_name="task-1",
        )
        completed = report_account_intelligence_worker_status(
            owner_id=self.user.pk,
            status="completed",
            task_name="task-1",
            result="worker_completed",
        )
        state.refresh_from_db()

        self.assertTrue(started["applied"])
        self.assertTrue(completed["applied"])
        self.assertFalse(state.pending_request)
        self.assertIsNotNone(state.last_started_at)
        self.assertIsNotNone(state.last_completed_at)
        self.assertEqual(state.last_result, "worker_completed")

    def test_report_worker_status_rejects_stale_task_completion(self):
        AccountIntelligenceDispatchState.objects.create(
            owner=self.user,
            pending_request=True,
            last_task_name="task-current",
            last_result="enqueued",
        )

        report = report_account_intelligence_worker_status(
            owner_id=self.user.pk,
            status="completed",
            task_name="task-old",
        )
        state = AccountIntelligenceDispatchState.objects.get(owner=self.user)

        self.assertFalse(report["applied"])
        self.assertEqual(report["result"], "stale_task")
        self.assertTrue(state.pending_request)
        self.assertEqual(state.last_result, "enqueued")

    @override_settings(ACCOUNTS_INTELLIGENCE_INTERNAL_TOKEN="worker-token")
    def test_worker_report_endpoint_requires_internal_token(self):
        view = AccountPortfolioSnapshotViewSet.as_view({"post": "worker_report"})

        request = self.factory.post(
            "/api/finance/accounts/snapshots-portafolio-cuenta/worker-report/",
            {
                "owner_id": str(self.user.pk),
                "status": "completed",
                "task_name": "task-1",
            },
            format="json",
            HTTP_X_VEXXO_INTERNAL_TOKEN="worker-token",
        )
        response = view(request)
        state = AccountIntelligenceDispatchState.objects.get(owner=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(state.pending_request)
