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
    get_account_event_runtime,
)
from finance.accounts.domain.guards import get_account_plan_snapshot, primary_account_limit_errors
from finance.accounts.models import Account, AccountMembership, AccountStatus, AccountType

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

    def test_primary_limit_errors_for_free_plan(self):
        Account.objects.create(owner=self.user, name="Principal", currency="COP", is_primary=True)

        errors = primary_account_limit_errors(self.user)

        self.assertIn("is_primary", errors)


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

        self.assertEqual(payload["account_id"], self.account.pk)
        self.assertEqual(payload["delta"], "5.50")
        self.assertEqual(payload["transaction_id"], 99)

    def test_build_account_sync_payload(self):
        payload = build_account_sync_payload(
            account=self.account,
            change="schedule_sync",
            extra={"worker": "sync-service"},
        )

        self.assertEqual(payload["account_id"], self.account.pk)
        self.assertEqual(payload["change"], "schedule_sync")
        self.assertTrue(payload["has_external_link"])
        self.assertEqual(payload["worker"], "sync-service")

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
