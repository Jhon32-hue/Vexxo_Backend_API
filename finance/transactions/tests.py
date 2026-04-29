from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from common.domain_events import EventContext, VexxoAppDomainEvent
from finance.accounts.models import Account, AccountMembership
from finance.debts.models import Debt, DebtInstallment
from finance.transactions.Models import (
    Transaction,
    TransactionDomainEventOutbox,
    TransactionExternalDetails,
    TransactionInferenceRequest,
    TransactionIntakeBatch,
    TransactionIntakeReceipt,
    TransactionReconciliationIssue,
    TransactionSourceLink,
)
from finance.transactions.Views.transactions_views import TransactionViewSet
from finance.transactions.domain_events import (
    TransactionDomainEventTypes,
    build_transaction_payload,
    serialize_transaction_state,
)
from finance.transactions.event_handlers import handle_transaction_side_effects
from finance.transactions.transaction_intake_service import (
    apply_intake_batch,
    receive_intake_batch,
    receive_single_intake_row,
)
from finance.transactions.transaction_inference_service import create_voice_transaction_inference_request
from finance.transactions.transaction_inference_dispatch_service import dispatch_transaction_inference
from finance.transactions.transaction_message_parser_service import parse_message_transaction
from finance.transactions.transaction_reconciliation_service import resolve_reconciliation_issue
from integrations_stub.banks.transaction_bridge import (
    process_stub_transactions_reconciliation_resolution,
    process_stub_transactions_sync_batch,
)
from integrations_stub.llm.services import process_stub_transaction_inference_request

User = get_user_model()


class TransactionEventActorTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="tx-actor",
            email="tx-actor@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Actor",
            currency="COP",
        )

    def _create_transaction(self):
        view = TransactionViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/finance/transactions/transactions/",
            {
                "account": self.account.pk,
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "12000.00",
                "date": "2026-04-03",
                "notes": "Compra semanal",
                "confirmed": True,
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, 201)
        return Transaction.objects.get(pk=response.data["id"])

    def test_create_update_delete_events_capture_actor_user_id(self):
        tx = self._create_transaction()

        created_events = TransactionDomainEventOutbox.objects.filter(
            event_type=TransactionDomainEventTypes.TRANSACTION_CREATED,
            aggregate_id=str(tx.pk),
        )
        self.assertEqual(created_events.count(), 1)
        created_event = created_events.latest("occurred_at")
        self.assertEqual(created_event.payload["actor_user_id"], str(self.user.id))

        update_view = TransactionViewSet.as_view({"patch": "partial_update"})
        update_request = self.factory.patch(
            f"/finance/transactions/transactions/{tx.pk}/",
            {"notes": "Compra semanal actualizada"},
            format="json",
        )
        force_authenticate(update_request, user=self.user)
        update_response = update_view(update_request, pk=tx.pk)
        self.assertEqual(update_response.status_code, 200)

        updated_events = TransactionDomainEventOutbox.objects.filter(
            event_type=TransactionDomainEventTypes.TRANSACTION_UPDATED,
            aggregate_id=str(tx.pk),
        )
        self.assertEqual(updated_events.count(), 1)
        updated_event = updated_events.latest("occurred_at")
        self.assertEqual(updated_event.payload["actor_user_id"], str(self.user.id))

        delete_view = TransactionViewSet.as_view({"delete": "destroy"})
        delete_request = self.factory.delete(f"/finance/transactions/transactions/{tx.pk}/")
        force_authenticate(delete_request, user=self.user)
        delete_response = delete_view(delete_request, pk=tx.pk)
        self.assertEqual(delete_response.status_code, 204)

        deleted_events = TransactionDomainEventOutbox.objects.filter(
            event_type=TransactionDomainEventTypes.TRANSACTION_DELETED,
            aggregate_id=str(tx.pk),
        )
        self.assertEqual(deleted_events.count(), 1)
        deleted_event = deleted_events.latest("occurred_at")
        self.assertEqual(deleted_event.payload["actor_user_id"], str(self.user.id))


class TransactionSharedAccessTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(
            username="owner-shared",
            email="owner-shared@example.com",
            password="secret123",
            plan="pro",
        )
        self.collaborator = User.objects.create_user(
            username="member-shared",
            email="member-shared@example.com",
            password="secret123",
            plan="free",
        )
        self.account = Account.objects.create(
            owner=self.owner,
            name="Cuenta Compartida",
            currency="COP",
            ownership="shared",
        )
        self.account.ensure_owner_membership()
        AccountMembership.objects.create(
            account=self.account,
            user=self.collaborator,
            role="member",
            access_mode="full",
            can_post_transactions=True,
            is_active=True,
        )
        self.tx = Transaction.objects.create(
            owner=self.owner,
            account=self.account,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.POSTED,
            amount=Decimal("45000.00"),
            date=date(2026, 4, 3),
            notes="Mercado compartido",
            confirmed=True,
        )

    def test_member_can_list_shared_transactions_with_scope_shared(self):
        view = TransactionViewSet.as_view({"get": "list"})
        request = self.factory.get("/finance/transactions/transactions/?scope=shared")
        force_authenticate(request, user=self.collaborator)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        ids = {str(item["id"]) for item in response.data}
        self.assertIn(str(self.tx.pk), ids)

    def test_member_creates_transaction_into_owner_ledger(self):
        view = TransactionViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/finance/transactions/transactions/",
            {
                "account": self.account.pk,
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "10000.00",
                "date": "2026-04-04",
                "notes": "Taxi compartido",
                "confirmed": True,
            },
            format="json",
        )
        force_authenticate(request, user=self.collaborator)
        response = view(request)

        self.assertEqual(response.status_code, 201)
        tx = Transaction.objects.get(pk=response.data["id"])
        self.assertEqual(tx.owner_id, self.owner.id)
        event = TransactionDomainEventOutbox.objects.filter(
            event_type=TransactionDomainEventTypes.TRANSACTION_CREATED,
            aggregate_id=str(tx.pk),
        ).latest("occurred_at")
        self.assertTrue(event.payload["shared_account"])
        self.assertEqual(event.payload["actor_user_id"], str(self.collaborator.id))


class TransactionFinancialReconciliationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tx-reconcile",
            email="tx-reconcile@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Deuda",
            currency="COP",
        )
        self.debt = Debt.objects.create(
            owner=self.user,
            name="Prestamo",
            principal=Decimal("100.00"),
            currency="COP",
            start_date=date(2026, 4, 1),
            total_installments=1,
            term_months=1,
            status="active",
        )
        self.installment = DebtInstallment.objects.filter(debt=self.debt).order_by("number").first()
        if not self.installment:
            self.installment = DebtInstallment.objects.create(
                owner=self.user,
                debt=self.debt,
                number=1,
                due_date=date(2026, 4, 10),
                amount_due=Decimal("100.00"),
            )

    def _event(self, event_type: str, payload: dict) -> VexxoAppDomainEvent:
        return VexxoAppDomainEvent(
            type=event_type,
            context=EventContext.TRANSACTIONS,
            payload=payload,
            metadata={"source": "finance.transactions.tests"},
        )

    def test_financial_update_reconciles_debt_payments(self):
        tx = Transaction.objects.create(
            owner=self.user,
            account=self.account,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.POSTED,
            amount=Decimal("100.00"),
            date=date(2026, 4, 3),
            debt=self.debt,
            installment=self.installment,
            confirmed=True,
        )

        created_payload = build_transaction_payload(tx, before={})
        handle_transaction_side_effects(self._event(TransactionDomainEventTypes.TRANSACTION_CREATED, created_payload))
        self.installment.refresh_from_db()
        self.assertEqual(self.installment.paid_amount, Decimal("100.00"))
        self.assertEqual(self.installment.status, "paid")

        before = serialize_transaction_state(tx)
        tx.amount = Decimal("40.00")
        tx.save(update_fields=["amount", "updated_at"])

        financial_payload = build_transaction_payload(tx, before=before)
        handle_transaction_side_effects(
            self._event(TransactionDomainEventTypes.TRANSACTION_FINANCIAL_UPDATED, financial_payload)
        )

        self.installment.refresh_from_db()
        self.debt.refresh_from_db()
        self.assertEqual(self.installment.paid_amount, Decimal("40.00"))
        self.assertEqual(self.installment.status, "partial")
        self.assertEqual(self.debt.status, "active")


class TransactionIntakeServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tx-intake",
            email="tx-intake@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Open Finance",
            currency="COP",
            provider="belvo",
            external_id="acct-ext-001",
        )

    def test_apply_batch_materializes_transaction_and_source_link(self):
        batch, created = receive_intake_batch(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-001",
            request_id="req-batch-001",
            idempotency_key="idem-batch-001",
            rows=[
                {
                    "type": Transaction.Type.EXPENSE,
                    "status": Transaction.Status.POSTED,
                    "amount": "12500.00",
                    "date": "2026-04-08",
                    "external_id": "txn-ext-001",
                    "description": "Compra supermercado",
                    "booking_datetime": "2026-04-08T10:15:00-05:00",
                    "merchant_name": "Supermercado Uno",
                    "merchant_category_code": "5411",
                    "counterparty_name": "Supermercado Uno SAS",
                    "rail": "open_banking",
                    "channel": "api",
                    "data_origin": "open_banking",
                    "confidence_score": 98,
                }
            ],
        )
        self.assertTrue(created)

        result = apply_intake_batch(batch=batch)
        self.assertEqual(result.counts["materialized"], 1)

        tx = Transaction.objects.get(external_id="txn-ext-001")
        self.assertEqual(tx.owner_id, self.user.id)
        self.assertEqual(tx.account_id, self.account.id)
        self.assertEqual(tx.source, "open_finance")
        self.assertEqual(tx.description, "Compra supermercado")
        self.assertEqual(tx.rail, Transaction.Rail.OPEN_BANKING)
        self.assertEqual(tx.channel, Transaction.Channel.API)
        self.assertEqual(tx.data_origin, Transaction.DataOrigin.OPEN_BANKING)
        self.assertEqual(tx.confidence_score, 98)
        self.assertEqual(tx.country_code, "")
        self.assertIsNotNone(tx.booking_datetime)

        link = TransactionSourceLink.objects.get(transaction=tx)
        self.assertEqual(link.provider, "belvo")
        self.assertEqual(link.provider_account_id, "acct-ext-001")
        details = TransactionExternalDetails.objects.get(transaction=tx)
        self.assertEqual(details.description, "Compra supermercado")
        self.assertEqual(details.merchant_name, "Supermercado Uno")
        self.assertEqual(details.merchant_category_code, "5411")
        self.assertEqual(details.counterparty_name, "Supermercado Uno SAS")
        self.assertEqual(details.rail, TransactionExternalDetails.Rail.OPEN_BANKING)
        self.assertEqual(details.channel, TransactionExternalDetails.Channel.API)
        self.assertEqual(details.data_origin, TransactionExternalDetails.DataOrigin.OPEN_BANKING)
        self.assertEqual(details.confidence_score, 98)
        self.assertIsNotNone(details.booking_datetime)

        self.assertTrue(
            TransactionDomainEventOutbox.objects.filter(
                event_type=TransactionDomainEventTypes.TRANSACTION_IMPORTED,
                aggregate_id=str(tx.pk),
            ).exists()
        )
        self.assertTrue(
            TransactionDomainEventOutbox.objects.filter(
                event_type=TransactionDomainEventTypes.TRANSACTION_INTAKE_BATCH_RECEIVED,
                aggregate_id=str(batch.pk),
            ).exists()
        )
        self.assertTrue(
            TransactionDomainEventOutbox.objects.filter(
                event_type=TransactionDomainEventTypes.TRANSACTION_INTAKE_BATCH_APPLIED,
                aggregate_id=str(batch.pk),
            ).exists()
        )

    def test_internal_intake_serializer_accepts_rich_external_fields(self):
        batch, created = receive_intake_batch(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-001",
            request_id="req-batch-rich-001",
            idempotency_key="idem-batch-rich-001",
            rows=[
                {
                    "type": Transaction.Type.EXPENSE,
                    "status": Transaction.Status.POSTED,
                    "amount": "8300.00",
                    "date": "2026-04-09",
                    "external_id": "txn-ext-rich-001",
                    "description": "Compra cafeteria",
                    "booking_datetime": "2026-04-09T08:00:00-05:00",
                    "value_datetime": "2026-04-09T09:00:00-05:00",
                    "credit_debit_indicator": "debit",
                    "rail": "open_banking",
                    "channel": "api",
                    "data_origin": "open_banking",
                    "confidence_score": 100,
                    "original_amount": "8300.00",
                    "original_currency": "COP",
                    "fx_rate": "1.00000000",
                }
            ],
        )
        self.assertTrue(created)
        result = apply_intake_batch(batch=batch)
        self.assertEqual(result.counts["materialized"], 1)
        tx = Transaction.objects.get(external_id="txn-ext-rich-001")
        self.assertEqual(tx.credit_debit_indicator, Transaction.CreditDebitIndicator.DEBIT)
        self.assertEqual(tx.rail, Transaction.Rail.OPEN_BANKING)
        self.assertEqual(tx.channel, Transaction.Channel.API)
        self.assertEqual(tx.data_origin, Transaction.DataOrigin.OPEN_BANKING)
        self.assertEqual(tx.confidence_score, 100)

    def test_voice_inferred_row_materializes_pending_manual_rail_transaction(self):
        result = receive_single_intake_row(
            provider="voice_ai",
            source="voice",
            provider_account_id="",
            request_id="req-voice-001",
            idempotency_key="idem-voice-001",
            row={
                "account_id": self.account.pk,
                "external_id": "voice-note-001",
                "provider_event_id": "voice-note-001",
                "provider_status": "inferred_pending_confirmation",
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.PENDING,
                "amount": "24900.00",
                "date": "2026-04-08",
                "description": "Compra en cafeteria",
                "parsed_text": "Registra un gasto de 24.900 en cafeteria",
                "parser_version": "transactions.voice_parser.v1",
                "needs_user_confirmation": True,
                "inference_status": TransactionExternalDetails.InferenceStatus.NEEDS_CONFIRMATION,
                "confidence_score": 82,
            },
        )

        self.assertEqual(result.counts["materialized"], 1)
        tx = Transaction.objects.get(external_id="voice-note-001")
        self.assertEqual(tx.status, Transaction.Status.PENDING)
        self.assertFalse(tx.confirmed)
        self.assertEqual(tx.rail, Transaction.Rail.MANUAL)
        self.assertEqual(tx.channel, Transaction.Channel.VOICE)
        self.assertEqual(tx.data_origin, Transaction.DataOrigin.INFERRED)

        details = TransactionExternalDetails.objects.get(transaction=tx)
        self.assertEqual(details.rail, TransactionExternalDetails.Rail.MANUAL)
        self.assertEqual(details.channel, TransactionExternalDetails.Channel.VOICE)
        self.assertEqual(details.data_origin, TransactionExternalDetails.DataOrigin.INFERRED)
        self.assertTrue(details.needs_user_confirmation)
        self.assertEqual(details.inference_status, TransactionExternalDetails.InferenceStatus.NEEDS_CONFIRMATION)

    def test_message_parser_service_infers_amount_type_and_description(self):
        parsed = parse_message_transaction(
            text="Compra por $12.500 en SUPERMERCADO EXITO con tu tarjeta terminada en 1234.",
            currency="COP",
        )
        self.assertEqual(parsed.amount, Decimal("12500.00"))
        self.assertEqual(parsed.tx_type, Transaction.Type.EXPENSE)
        self.assertIn("SUPERMERCADO EXITO", parsed.description)
        self.assertGreaterEqual(parsed.confidence_score, 70)

    def test_single_row_duplicate_does_not_duplicate_ledger(self):
        first = receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-001",
            request_id="req-row-001",
            idempotency_key="idem-row-001",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "31000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-dup-001",
                "description": "Pago PSE",
            },
        )
        self.assertEqual(first.counts["materialized"], 1)

        second = receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-001",
            request_id="req-row-002",
            idempotency_key="idem-row-002",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "31000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-dup-001",
                "description": "Pago PSE",
            },
        )
        self.assertEqual(second.counts["duplicate"], 1)
        self.assertEqual(Transaction.objects.filter(external_id="txn-ext-dup-001").count(), 1)

        receipt = TransactionIntakeReceipt.objects.filter(external_id="txn-ext-dup-001").latest("first_seen_at")
        self.assertEqual(receipt.status, TransactionIntakeReceipt.Status.DUPLICATE)
        self.assertTrue(
            TransactionDomainEventOutbox.objects.filter(
                event_type=TransactionDomainEventTypes.TRANSACTION_INTAKE_ROW_DUPLICATE_DETECTED,
                aggregate_id=str(receipt.pk),
            ).exists()
        )

    def test_material_change_on_countable_transaction_creates_reconciliation_issue(self):
        initial = receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-001",
            request_id="req-row-003",
            idempotency_key="idem-row-003",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "45000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-correct-001",
                "description": "Compra tienda",
            },
        )
        self.assertEqual(initial.counts["materialized"], 1)
        tx = Transaction.objects.get(external_id="txn-ext-correct-001")

        follow_up = receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-001",
            request_id="req-row-004",
            idempotency_key="idem-row-004",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "65000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-correct-001",
                "description": "Compra tienda corregida",
            },
        )
        self.assertEqual(follow_up.counts["corrected"], 1)

        tx.refresh_from_db()
        self.assertEqual(tx.amount, Decimal("45000.00"))
        issue = TransactionReconciliationIssue.objects.get(transaction=tx)
        self.assertEqual(issue.issue_type, TransactionReconciliationIssue.IssueType.CORRECTION_REQUIRED)
        self.assertTrue(
            TransactionDomainEventOutbox.objects.filter(
                event_type=TransactionDomainEventTypes.TRANSACTION_CORRECTED,
                aggregate_id=str(issue.pk),
            ).exists()
        )


class TransactionReconciliationResolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="tx-recon-resolution",
            email="tx-recon-resolution@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Reconciliation",
            currency="COP",
            provider="belvo",
            external_id="acct-ext-recon-001",
        )
        self.secondary_account = Account.objects.create(
            owner=self.user,
            name="Cuenta Reconciliation 2",
            currency="COP",
            provider="belvo",
            external_id="acct-ext-recon-002",
        )

    def _create_corrected_issue(self):
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            request_id="req-recon-001",
            idempotency_key="idem-recon-001",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "45000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-recon-001",
                "description": "Compra base",
            },
        )
        tx = Transaction.objects.get(external_id="txn-ext-recon-001")
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            request_id="req-recon-002",
            idempotency_key="idem-recon-002",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "65000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-recon-001",
                "description": "Compra corregida",
            },
        )
        issue = TransactionReconciliationIssue.objects.get(transaction=tx)
        return tx, issue

    def _create_reversal_issue(self):
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            request_id="req-rev-001",
            idempotency_key="idem-rev-001",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "21000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-rev-001",
                "description": "Compra a revertir",
            },
        )
        tx = Transaction.objects.get(external_id="txn-ext-rev-001")
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            request_id="req-rev-002",
            idempotency_key="idem-rev-002",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.CANCELED,
                "provider_status": "reversed",
                "amount": "21000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-rev-001",
                "description": "Compra revertida",
            },
        )
        issue = TransactionReconciliationIssue.objects.get(transaction=tx)
        return tx, issue

    def test_correction_issue_can_create_adjustment_transaction(self):
        tx, issue = self._create_corrected_issue()

        resolved = resolve_reconciliation_issue(
            issue=issue,
            action=TransactionReconciliationIssue.ResolutionAction.CREATE_ADJUSTMENT,
            actor=self.user,
            notes="Resolver con ajuste compensatorio.",
        )

        resolved.refresh_from_db()
        self.assertEqual(resolved.status, TransactionReconciliationIssue.Status.RESOLVED)
        self.assertEqual(resolved.resolution_action, TransactionReconciliationIssue.ResolutionAction.CREATE_ADJUSTMENT)
        self.assertIsNotNone(resolved.resolution_transaction_id)
        adjustment = resolved.resolution_transaction
        self.assertEqual(adjustment.source, "reconciliation_adjustment")
        self.assertEqual(adjustment.type, Transaction.Type.EXPENSE)
        self.assertEqual(adjustment.amount, Decimal("20000.00"))
        self.assertEqual(tx.amount, Decimal("45000.00"))
        self.assertTrue(
            TransactionDomainEventOutbox.objects.filter(
                event_type="transactions.reconciliation.issue.resolved.v1",
                aggregate_id=str(issue.pk),
            ).exists()
        )

    def test_reverse_issue_can_create_reversal_transaction(self):
        tx, issue = self._create_reversal_issue()

        resolved = resolve_reconciliation_issue(
            issue=issue,
            action=TransactionReconciliationIssue.ResolutionAction.CREATE_REVERSAL,
            actor=self.user,
            notes="Resolver con reverso formal.",
        )

        resolved.refresh_from_db()
        self.assertEqual(resolved.status, TransactionReconciliationIssue.Status.RESOLVED)
        self.assertEqual(resolved.resolution_action, TransactionReconciliationIssue.ResolutionAction.CREATE_REVERSAL)
        reversal = resolved.resolution_transaction
        self.assertIsNotNone(reversal)
        self.assertEqual(reversal.source, "reconciliation_reverse")
        self.assertEqual(reversal.type, Transaction.Type.INCOME)
        self.assertEqual(reversal.amount, Decimal("21000.00"))
        self.assertEqual(tx.amount, Decimal("21000.00"))

    def test_complex_correction_can_create_replacement_pair_and_relink_source(self):
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            request_id="req-complex-001",
            idempotency_key="idem-complex-001",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "30000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-complex-001",
                "description": "Compra original",
            },
        )
        original_tx = Transaction.objects.get(external_id="txn-ext-complex-001")
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            request_id="req-complex-002",
            idempotency_key="idem-complex-002",
            row={
                "type": Transaction.Type.INCOME,
                "status": Transaction.Status.POSTED,
                "amount": "30500.00",
                "date": "2026-04-09",
                "external_id": "txn-ext-complex-001",
                "internal_account_id": self.secondary_account.pk,
                "description": "Correccion compleja",
            },
        )
        issue = TransactionReconciliationIssue.objects.get(transaction=original_tx)

        resolved = resolve_reconciliation_issue(
            issue=issue,
            action=TransactionReconciliationIssue.ResolutionAction.CREATE_ADJUSTMENT,
            actor=self.user,
            notes="Resolver con replacement pair.",
        )

        resolved.refresh_from_db()
        replacement = resolved.resolution_transaction
        self.assertEqual(resolved.status, TransactionReconciliationIssue.Status.RESOLVED)
        self.assertEqual(replacement.source, "reconciliation_replacement")
        self.assertEqual(replacement.account_id, self.secondary_account.id)
        self.assertEqual(replacement.type, Transaction.Type.INCOME)
        self.assertEqual(replacement.amount, Decimal("30500.00"))
        replacement_pair = resolved.resolution_payload.get("replacement_pair") or {}
        reversal_id = replacement_pair.get("reversal_transaction_id")
        self.assertTrue(reversal_id)
        reversal = Transaction.objects.get(pk=reversal_id)
        self.assertEqual(reversal.source, "reconciliation_reverse")
        self.assertEqual(reversal.account_id, original_tx.account_id)
        link = TransactionSourceLink.objects.get(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            external_id="txn-ext-complex-001",
        )
        self.assertEqual(link.transaction_id, replacement.id)

    def test_apply_provider_update_rejects_complex_change(self):
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            request_id="req-complex-003",
            idempotency_key="idem-complex-003",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "12000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-complex-002",
                "description": "Base apply reject",
            },
        )
        tx = Transaction.objects.get(external_id="txn-ext-complex-002")
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-recon-001",
            request_id="req-complex-004",
            idempotency_key="idem-complex-004",
            row={
                "type": Transaction.Type.INCOME,
                "status": Transaction.Status.POSTED,
                "amount": "12500.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-complex-002",
                "internal_account_id": self.secondary_account.pk,
                "description": "Cambio complejo reject",
            },
        )
        issue = TransactionReconciliationIssue.objects.get(transaction=tx)

        with self.assertRaisesMessage(
            ValueError,
            "Esta correccion cambia cuenta, tipo o proveedor. Usa create_adjustment para replacement pair formal.",
        ):
            resolve_reconciliation_issue(
                issue=issue,
                action=TransactionReconciliationIssue.ResolutionAction.APPLY_PROVIDER_UPDATE,
                actor=self.user,
            )


@override_settings(TRANSACTIONS_INTAKE_INTERNAL_TOKEN="internal-transactions-token")
class TransactionIntakeInternalApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="tx-intake-api",
            email="tx-intake-api@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta API Intake",
            currency="COP",
            provider="belvo",
            external_id="acct-ext-api-001",
        )

    def test_internal_batch_endpoints_receive_and_apply(self):
        create_response = self.client.post(
            "/api/internal/transactions/intake/batches/",
            {
                "provider": "belvo",
                "source": "open_finance",
                "provider_account_id": "acct-ext-api-001",
                "rows": [
                    {
                        "type": "expense",
                        "status": "posted",
                        "amount": "7800.00",
                        "date": "2026-04-08",
                        "external_id": "txn-ext-api-001",
                        "description": "Cafe",
                    }
                ],
            },
            format="json",
            HTTP_X_VEXXO_INTERNAL_TOKEN="internal-transactions-token",
            HTTP_X_REQUEST_ID="req-api-001",
            HTTP_IDEMPOTENCY_KEY="idem-api-001",
        )
        self.assertEqual(create_response.status_code, 201)
        batch_id = create_response.data["batch"]["id"]

        apply_response = self.client.post(
            f"/api/internal/transactions/intake/batches/{batch_id}/apply/",
            {},
            format="json",
            HTTP_X_VEXXO_INTERNAL_TOKEN="internal-transactions-token",
            HTTP_X_REQUEST_ID="req-api-002",
            HTTP_IDEMPOTENCY_KEY="idem-api-apply-001",
        )
        self.assertEqual(apply_response.status_code, 200)
        self.assertEqual(apply_response.data["counts"]["materialized"], 1)
        self.assertTrue(Transaction.objects.filter(external_id="txn-ext-api-001").exists())

    def test_internal_message_intake_endpoint_materializes_pending_transaction(self):
        response = self.client.post(
            "/api/internal/transactions/intake/message/",
            {
                "provider": "message_parser",
                "source": "sms",
                "internal_account_id": self.account.pk,
                "message_id": "msg-001",
                "sender_id": "BANCOXYZ",
                "received_at": "2026-04-08T12:00:00-05:00",
                "text": "Compra por $12.500 en SUPERMERCADO EXITO con tu tarjeta.",
            },
            format="json",
            HTTP_X_VEXXO_INTERNAL_TOKEN="internal-transactions-token",
            HTTP_X_REQUEST_ID="req-api-msg-001",
            HTTP_IDEMPOTENCY_KEY="idem-api-msg-001",
        )
        self.assertEqual(response.status_code, 201)
        tx = Transaction.objects.get(external_id="msg-001")
        self.assertEqual(tx.status, Transaction.Status.PENDING)
        self.assertFalse(tx.confirmed)
        self.assertEqual(tx.rail, Transaction.Rail.MESSAGE)
        self.assertEqual(tx.channel, Transaction.Channel.SMS)
        self.assertEqual(tx.data_origin, Transaction.DataOrigin.INFERRED)
        self.assertTrue(tx.description)
        details = TransactionExternalDetails.objects.get(transaction=tx)
        self.assertTrue(details.needs_user_confirmation)
        self.assertEqual(details.inference_status, TransactionExternalDetails.InferenceStatus.NEEDS_CONFIRMATION)
        self.assertEqual(details.message_id, "msg-001")

    def test_internal_voice_intake_row_endpoint_materializes_pending_transaction(self):
        response = self.client.post(
            "/api/internal/transactions/intake/row/",
            {
                "provider": "voice_ai",
                "source": "voice",
                "row": {
                    "internal_account_id": self.account.pk,
                    "external_id": "voice-api-001:item-001",
                    "provider_event_id": "voice-api-001:item-001",
                    "provider_status": "inferred_pending_confirmation",
                    "type": "expense",
                    "status": "pending",
                    "amount": "24900.00",
                    "date": "2026-04-08",
                    "currency": "COP",
                    "confirmed": False,
                    "rail": "manual",
                    "channel": "voice",
                    "data_origin": "inferred",
                    "description": "Compra en farmacia",
                    "parsed_text": "Registra un gasto de 24.900 en farmacia",
                    "parser_version": "transactions.voice_parser.v1",
                    "needs_user_confirmation": True,
                    "inference_status": "needs_confirmation",
                    "confidence_score": 82,
                },
            },
            format="json",
            HTTP_X_VEXXO_INTERNAL_TOKEN="internal-transactions-token",
            HTTP_X_REQUEST_ID="req-api-voice-001",
            HTTP_IDEMPOTENCY_KEY="idem-api-voice-001",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["counts"]["materialized"], 1)
        tx = Transaction.objects.get(external_id="voice-api-001:item-001")
        self.assertEqual(tx.status, Transaction.Status.PENDING)
        self.assertFalse(tx.confirmed)
        self.assertEqual(tx.rail, Transaction.Rail.MANUAL)
        self.assertEqual(tx.channel, Transaction.Channel.VOICE)
        self.assertEqual(tx.data_origin, Transaction.DataOrigin.INFERRED)

        details = TransactionExternalDetails.objects.get(transaction=tx)
        self.assertTrue(details.needs_user_confirmation)
        self.assertEqual(details.inference_status, TransactionExternalDetails.InferenceStatus.NEEDS_CONFIRMATION)

    def test_internal_reconciliation_resolution_endpoint(self):
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-api-001",
            request_id="req-api-recon-001",
            idempotency_key="idem-api-recon-001",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "10000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-api-recon-001",
                "description": "Compra base api",
            },
        )
        tx = Transaction.objects.get(external_id="txn-ext-api-recon-001")
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-api-001",
            request_id="req-api-recon-002",
            idempotency_key="idem-api-recon-002",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "15000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-api-recon-001",
                "description": "Compra corregida api",
            },
        )
        issue = TransactionReconciliationIssue.objects.get(transaction=tx)

        response = self.client.post(
            f"/api/internal/transactions/reconciliation/issues/{issue.pk}/resolve/",
            {
                "action": TransactionReconciliationIssue.ResolutionAction.CREATE_ADJUSTMENT,
                "notes": "Resolver via endpoint interno.",
            },
            format="json",
            HTTP_X_VEXXO_INTERNAL_TOKEN="internal-transactions-token",
            HTTP_X_REQUEST_ID="req-api-recon-003",
            HTTP_IDEMPOTENCY_KEY="idem-api-recon-003",
        )

        self.assertEqual(response.status_code, 200)
        issue.refresh_from_db()
        self.assertEqual(issue.status, TransactionReconciliationIssue.Status.RESOLVED)
        self.assertEqual(issue.resolution_action, TransactionReconciliationIssue.ResolutionAction.CREATE_ADJUSTMENT)
        self.assertTrue(Transaction.objects.filter(source="reconciliation_adjustment").exists())


class TransactionInferenceRequestApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="tx-inference-api",
            email="tx-inference-api@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Voz",
            currency="COP",
        )
        self.client.force_authenticate(user=self.user)

    def test_mobile_can_create_and_read_voice_inference_request(self):
        response = self.client.post(
            "/api/finance/transactions/inference-requests/",
            {
                "account_id": self.account.pk,
                "audio_object_ref": "gs://vexxo-audio/voice-001.m4a",
                "audio_content_type": "audio/mp4",
                "audio_duration_ms": 3500,
                "language": "es-CO",
            },
            format="json",
            HTTP_X_REQUEST_ID="req-voice-mobile-001",
            HTTP_IDEMPOTENCY_KEY="idem-voice-mobile-001",
        )

        self.assertEqual(response.status_code, 201)
        request_id = response.data["inference_request"]["id"]
        inference_request = TransactionInferenceRequest.objects.get(pk=request_id)
        self.assertEqual(inference_request.owner_id, self.user.id)
        self.assertEqual(inference_request.requested_by_id, self.user.id)
        self.assertEqual(inference_request.status, TransactionInferenceRequest.Status.QUEUED)

        detail_response = self.client.get(f"/api/finance/transactions/inference-requests/{request_id}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["id"], request_id)

    def test_mobile_create_rejects_client_injected_raw_payload(self):
        response = self.client.post(
            "/api/finance/transactions/inference-requests/",
            {
                "account_id": self.account.pk,
                "audio_object_ref": "gs://vexxo-audio/voice-unsafe-001.m4a",
                "raw_payload": {
                    "normalized_rows": [
                        {
                            "type": "expense",
                            "amount": "24900.00",
                            "date": "2026-04-08",
                            "description": "Cliente intenta inyectar filas",
                        }
                    ]
                },
            },
            format="json",
            HTTP_X_REQUEST_ID="req-voice-mobile-unsafe-001",
            HTTP_IDEMPOTENCY_KEY="idem-voice-mobile-unsafe-001",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("raw_payload", response.data)

    def test_stub_llm_processes_request_through_canonical_intake(self):
        inference_request, created = create_voice_transaction_inference_request(
            actor=self.user,
            account=self.account,
            request_id="req-voice-stub-001",
            idempotency_key="idem-voice-stub-001",
            audio_object_ref="gs://vexxo-audio/voice-002.m4a",
            raw_payload={
                "transcript": "Registra gasto de 18000 en cafe",
                "transcript_confidence": "0.9200",
                "normalized_rows": [
                    {
                        "type": "expense",
                        "amount": "18000.00",
                        "date": "2026-04-08",
                        "description": "Cafe",
                    }
                ],
            },
        )
        self.assertTrue(created)

        result = process_stub_transaction_inference_request(
            inference_request_id=inference_request.pk,
            request_id="req-voice-stub-worker-001",
            source="tests",
        )

        self.assertEqual(result["result"], "processed")
        inference_request.refresh_from_db()
        self.assertEqual(inference_request.status, TransactionInferenceRequest.Status.APPLIED)
        self.assertIsNotNone(inference_request.intake_batch_id)
        tx = Transaction.objects.get(external_id=f"{inference_request.pk}:item-1")
        self.assertEqual(tx.status, Transaction.Status.PENDING)
        self.assertFalse(tx.confirmed)
        self.assertEqual(tx.channel, Transaction.Channel.VOICE)

    def test_stub_llm_skips_terminal_request(self):
        inference_request = TransactionInferenceRequest.objects.create(
            owner=self.user,
            requested_by=self.user,
            account=self.account,
            source=TransactionInferenceRequest.Source.VOICE,
            provider="voice_ai",
            request_id="req-voice-terminal-001",
            idempotency_key="idem-voice-terminal-001",
            status=TransactionInferenceRequest.Status.APPLIED,
            audio_object_ref="gs://vexxo-audio/voice-terminal.m4a",
            raw_payload={
                "normalized_rows": [
                    {
                        "type": "expense",
                        "amount": "18000.00",
                        "date": "2026-04-08",
                        "description": "No debe reprocesarse",
                    }
                ]
            },
        )

        result = process_stub_transaction_inference_request(
            inference_request_id=inference_request.pk,
            request_id="req-voice-terminal-worker-001",
            source="tests",
        )

        self.assertEqual(result["result"], "skipped")
        inference_request.refresh_from_db()
        self.assertEqual(inference_request.status, TransactionInferenceRequest.Status.APPLIED)
        self.assertFalse(Transaction.objects.filter(external_id=f"{inference_request.pk}:item-1").exists())

    def test_failed_voice_inference_can_be_retried(self):
        inference_request = TransactionInferenceRequest.objects.create(
            owner=self.user,
            requested_by=self.user,
            account=self.account,
            source=TransactionInferenceRequest.Source.VOICE,
            provider="voice_ai",
            request_id="req-voice-failed-001",
            idempotency_key="idem-voice-failed-001",
            status=TransactionInferenceRequest.Status.EXTRACTION_FAILED,
            audio_object_ref="gs://vexxo-audio/voice-failed.m4a",
            retry_count=4,
            last_error="No rows.",
            failed_at=timezone.now(),
            processing_started_at=timezone.now(),
        )

        response = self.client.post(f"/api/finance/transactions/inference-requests/{inference_request.pk}/retry/")

        self.assertEqual(response.status_code, 200)
        inference_request.refresh_from_db()
        self.assertEqual(inference_request.status, TransactionInferenceRequest.Status.QUEUED)
        self.assertEqual(inference_request.retry_count, 0)
        self.assertEqual(inference_request.last_error, "")
        self.assertIsNone(inference_request.failed_at)
        self.assertIsNone(inference_request.processing_started_at)


class TransactionInferenceDispatchServiceTests(TestCase):
    @patch("finance.transactions.transaction_inference_dispatch_service.enqueue_transaction_inference_task")
    def test_dispatch_treats_already_enqueued_as_success(self, enqueue_mock):
        enqueue_mock.return_value = {
            "result": "already_enqueued",
            "task_name": "projects/demo/locations/us-central1/queues/q/tasks/tx-inference-1",
        }

        result = dispatch_transaction_inference(
            inference_request_id="inference-1",
            request_id="req-dispatch-001",
            source="tests",
        )

        self.assertEqual(result["result"], "already_enqueued")
        self.assertIn("task_name", result)

    @override_settings(
        TRANSACTION_INFERENCE_CLOUD_TASKS_ENABLED=False,
        TRANSACTION_INFERENCE_LOCAL_FALLBACK_ENABLED=True,
    )
    @patch("finance.transactions.transaction_inference_dispatch_service._dispatch_local_fallback_async")
    def test_dispatch_uses_background_local_fallback(self, local_fallback_mock):
        local_fallback_mock.return_value = {
            "result": "local_fallback_enqueued",
            "mode": "background_thread",
            "inference_request_id": "inference-2",
        }

        result = dispatch_transaction_inference(
            inference_request_id="inference-2",
            request_id="req-dispatch-002",
            source="tests",
        )

        self.assertEqual(result["result"], "local_fallback_enqueued")
        local_fallback_mock.assert_called_once()


class IntegrationsStubTransactionsBridgeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="stub-bridge",
            email="stub-bridge@example.com",
            password="secret123",
            plan="pro",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Cuenta Stub Bridge",
            currency="COP",
            provider="belvo",
            external_id="acct-ext-stub-001",
        )

    def test_stub_bridge_can_process_transactions_sync_batch(self):
        result = process_stub_transactions_sync_batch(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-stub-001",
            request_id="req-stub-001",
            idempotency_key="idem-stub-001",
            rows=[
                {
                    "type": Transaction.Type.EXPENSE,
                    "status": Transaction.Status.POSTED,
                    "amount": "9900.00",
                    "date": "2026-04-08",
                    "external_id": "txn-ext-stub-001",
                    "description": "Bridge sync",
                }
            ],
        )
        self.assertEqual(result["counts"]["materialized"], 1)
        self.assertTrue(Transaction.objects.filter(external_id="txn-ext-stub-001").exists())

    def test_stub_bridge_can_resolve_reconciliation_issue(self):
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-stub-001",
            request_id="req-stub-002",
            idempotency_key="idem-stub-002",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "11000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-stub-002",
                "description": "Bridge resolution base",
            },
        )
        tx = Transaction.objects.get(external_id="txn-ext-stub-002")
        receive_single_intake_row(
            provider="belvo",
            source="open_finance",
            provider_account_id="acct-ext-stub-001",
            request_id="req-stub-003",
            idempotency_key="idem-stub-003",
            row={
                "type": Transaction.Type.EXPENSE,
                "status": Transaction.Status.POSTED,
                "amount": "13000.00",
                "date": "2026-04-08",
                "external_id": "txn-ext-stub-002",
                "description": "Bridge resolution corrected",
            },
        )
        issue = TransactionReconciliationIssue.objects.get(transaction=tx)

        result = process_stub_transactions_reconciliation_resolution(
            issue_id=issue.pk,
            action=TransactionReconciliationIssue.ResolutionAction.CREATE_ADJUSTMENT,
            notes="Resolver desde el stub.",
        )

        self.assertEqual(result["status"], TransactionReconciliationIssue.Status.RESOLVED)
        self.assertEqual(result["resolution_action"], TransactionReconciliationIssue.ResolutionAction.CREATE_ADJUSTMENT)
