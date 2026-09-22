from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from alerts.alerts.models.alerts import Alert
from alerts.alerts.services import generate_scheduled_payment_alerts
from finance.accounts.models import Account
from finance.budgets.models import SharedBudget
from finance.categories.models import Category
from finance.debts.models import Debt, DebtInstallment
from finance.transactions.payment_materialization_service import materialize_transaction_from_payment_intent
from identity.users.services.product_usage_projection_service import compute_user_usage_snapshot_from_oltp
from notifications.deliveries.models import NotificationDelivery
from payments.payment_intents.models import PaymentDomainEventOutbox, PaymentIntent
from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate
from payments.scheduled_payments.serializers import PaymentScheduleRunRequestSerializer, PaymentTemplateSerializer
from payments.scheduled_payments.services import (
    cancel_schedule_run,
    create_payment_intent_from_schedule_run,
    create_payment_template,
    get_schedule_run_operational_metrics,
    mark_schedule_run_paid,
    process_due_schedule_runs,
    retry_failed_schedule_run,
    sync_schedule_run_from_payment_intent_status,
    update_payment_template,
)
from realtime.consumers.models import RealtimeSignal
from rest_framework.test import APIClient
from social.teams.models import Membership, Team

User = get_user_model()


def _aware_dt(year, month, day, hour=9, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute), timezone.get_current_timezone())


@override_settings(DOMAIN_EVENTS_LOCAL_AUTOPUBLISH_ENABLED=False)
class PaymentTemplateBudgetAttributionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="secret123A",
        )
        self.partner = User.objects.create_user(
            username="partner",
            email="partner@example.com",
            password="secret123A",
        )
        self.account = Account.objects.create(owner=self.user, name="Cuenta principal")
        self.category = Category.objects.create(owner=self.user, name="Vivienda", type="expense")
        self.team = Team.objects.create(owner=self.user, name="Pareja", description="Team pareja")
        Membership.objects.create(team=self.team, user=self.partner, role="accountant", is_active=True)
        self.shared_budget = SharedBudget.objects.create(
            owner=self.user,
            team=self.team,
            name="Arriendo pareja",
            month="2026-05",
            amount="900.00",
        )
        self.debt = Debt.objects.create(
            owner=self.user,
            name="Credito libre inversion",
            principal="1200.00",
            currency="COP",
            start_date=timezone.localdate(),
        )
        self.installment = DebtInstallment.objects.create(
            owner=self.user,
            debt=self.debt,
            number=1,
            due_date=timezone.localdate(),
            amount_due="120.00",
        )

    def test_create_payment_template_defaults_to_personal_budget_scope(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Arriendo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="500.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
        )

        self.assertEqual(template.budget_scope, "personal")
        self.assertEqual(template.budget_attribution_source, "system_default")
        event = PaymentDomainEventOutbox.objects.filter(event_type="payments.recurring.template.created.v1").latest("occurred_at")
        self.assertEqual(event.payload["budget_scope"], "personal")
        self.assertEqual(event.payload["shared_budget_id"], "")

    def test_template_creation_is_idempotent_per_owner(self):
        first = create_payment_template(
            owner=self.user,
            account=self.account,
            name="Internet",
            default_amount="120.00",
            currency="COP",
            idempotency_key="mobile-scheduled-1",
        )
        replay = create_payment_template(
            owner=self.user,
            account=self.account,
            name="Internet",
            default_amount="120.00",
            currency="COP",
            idempotency_key="mobile-scheduled-1",
        )
        self.assertEqual(first.pk, replay.pk)
        self.assertTrue(replay._idempotent_replay)

        with self.assertRaisesMessage(ValueError, "Idempotency-Key"):
            create_payment_template(
                owner=self.user,
                account=self.account,
                name="Internet alterado",
                default_amount="130.00",
                currency="COP",
                idempotency_key="mobile-scheduled-1",
            )

    def test_public_template_execution_defaults_reject_reserved_keys(self):
        serializer = PaymentTemplateSerializer(
            data={
                "name": "Arriendo",
                "payment_type": PaymentTemplate.PaymentType.BILL,
                "amount_mode": PaymentTemplate.AmountMode.FIXED,
                "default_amount": "500.00",
                "currency": "COP",
                "cadence": PaymentTemplate.Cadence.MONTHLY,
                "execution_defaults": {"legacy_source": "transactions.ScheduledPayment"},
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("execution_defaults", serializer.errors)

    def test_request_run_payload_rejects_reserved_internal_keys(self):
        serializer = PaymentScheduleRunRequestSerializer(
            data={
                "scheduled_for": _aware_dt(2026, 5, 20).isoformat(),
                "run_payload": {"retry_of_schedule_run_id": "123"},
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("run_payload", serializer.errors)

    def test_update_payment_template_can_move_to_shared_budget_and_emits_payload(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Arriendo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="500.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
        )

        updated = update_payment_template(
            template,
            budget_scope="shared",
            shared_budget=self.shared_budget,
        )

        self.assertEqual(updated.budget_scope, "shared")
        self.assertEqual(updated.shared_budget_id, self.shared_budget.id)
        event = PaymentDomainEventOutbox.objects.filter(event_type="payments.recurring.template.updated.v1").latest("occurred_at")
        self.assertEqual(event.payload["budget_scope"], "shared")
        self.assertEqual(event.payload["shared_budget_id"], str(self.shared_budget.id))
        self.assertIn("budget_scope", event.payload["changed_fields"])

    def test_creating_active_template_bootstraps_scheduled_run(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Netflix",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="39.90",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 10),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        self.assertEqual(run.status, PaymentScheduleRun.Status.SCHEDULED)
        self.assertEqual(str(run.expected_amount), "39.90")
        self.assertEqual(run.due_on.isoformat(), "2026-05-10")

    def test_processing_due_runs_creates_notification_and_realtime_signal(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Arriendo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="500.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 5),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        summary = process_due_schedule_runs(as_of_date=run.due_on)
        run.refresh_from_db()
        self.assertEqual(run.status, PaymentScheduleRun.Status.DUE)
        self.assertEqual(run.reminder_stage, 1)
        self.assertEqual(summary["reminders_sent"], 1)
        self.assertTrue(
            NotificationDelivery.objects.filter(
                owner=self.user,
                dedupe_key=f"payment-schedule-run:{run.pk}:stage:1",
            ).exists()
        )
        self.assertTrue(
            RealtimeSignal.objects.filter(
                owner_id=self.user.id,
                aggregate_type="payment_schedule_run",
                aggregate_id=str(run.pk),
            ).exists()
        )

    def test_mark_paid_outside_materializes_transaction_and_closes_run(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Arriendo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="500.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 5),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        run = mark_schedule_run_paid(run, actor=self.user, paid_outside_vexxo=True, notes="Pagado en efectivo")
        run.refresh_from_db()
        self.assertEqual(run.status, PaymentScheduleRun.Status.PAID_OUTSIDE_VEXXO)
        self.assertIsNotNone(run.materialized_transaction_id)
        self.assertEqual(run.materialized_transaction.source, "scheduled_payment")
        self.assertEqual(run.materialized_transaction.raw_payload["payment_schedule_run_id"], str(run.pk))
        self.assertEqual(run.materialized_transaction.payment_schedule_run_id, run.pk)

    def test_mark_paid_is_blocked_when_payment_intent_is_active(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Arriendo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="500.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 5),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        intent = create_payment_intent_from_schedule_run(run, provider="sandbox", rail="other")
        intent.mark_processing()
        with self.assertRaisesMessage(ValueError, "PaymentIntent activo o ya liquidado"):
            mark_schedule_run_paid(run, actor=self.user, paid_outside_vexxo=False)

    def test_failed_run_remains_terminal_during_due_processing(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Servicio",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="120.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 5),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        run.status = PaymentScheduleRun.Status.FAILED
        run.failure_message = "provider timeout"
        run.save(update_fields=["status", "failure_message", "updated_at"])

        summary = process_due_schedule_runs(as_of_date=run.due_on)
        run.refresh_from_db()

        self.assertEqual(run.status, PaymentScheduleRun.Status.FAILED)
        self.assertEqual(summary["processed"], 0)

    def test_updating_next_run_at_supersedes_open_run_without_intent(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Netflix",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="39.90",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 10),
        )
        original_run = PaymentScheduleRun.objects.get(template=template)

        updated = update_payment_template(template, next_run_at=_aware_dt(2026, 5, 12))
        new_run = PaymentScheduleRun.objects.get(template=updated, scheduled_for=_aware_dt(2026, 5, 12))
        original_run.refresh_from_db()

        self.assertEqual(original_run.status, PaymentScheduleRun.Status.CANCELED)
        self.assertEqual(original_run.resolution_action, PaymentScheduleRun.ResolutionAction.CANCEL)
        self.assertNotEqual(original_run.pk, new_run.pk)

    def test_sync_from_payment_intent_status_marks_run_paid(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Arriendo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="500.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 5),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        intent = create_payment_intent_from_schedule_run(run, provider="sandbox", rail="other")
        intent.mark_succeeded()

        synced = sync_schedule_run_from_payment_intent_status(payment_intent=intent)
        synced.refresh_from_db()

        self.assertEqual(synced.status, PaymentScheduleRun.Status.PAID)
        self.assertEqual(synced.resolution_action, PaymentScheduleRun.ResolutionAction.PAY_WITH_VEXXO)
        self.assertIsNotNone(synced.paid_at)

    def test_sync_from_payment_intent_failure_marks_run_failed(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Arriendo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="500.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 5),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        intent = create_payment_intent_from_schedule_run(run, provider="sandbox", rail="other")
        intent.mark_failed(failure_message="rechazado")

        synced = sync_schedule_run_from_payment_intent_status(payment_intent=intent)
        synced.refresh_from_db()

        self.assertEqual(synced.status, PaymentScheduleRun.Status.FAILED)
        self.assertEqual(synced.failure_message, "rechazado")

    def test_template_amount_update_syncs_mutable_open_run(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Internet",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="89.90",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 15),
        )
        run = PaymentScheduleRun.objects.get(template=template)

        updated = update_payment_template(template, default_amount="99.90")
        run.refresh_from_db()

        self.assertEqual(updated.default_amount, run.expected_amount)

    def test_retry_failed_schedule_run_creates_replacement_occurrence(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Arriendo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="500.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 5),
        )
        failed_run = PaymentScheduleRun.objects.get(template=template)
        failed_run.status = PaymentScheduleRun.Status.FAILED
        failed_run.failure_message = "rechazado"
        failed_run.save(update_fields=["status", "failure_message", "updated_at"])

        replacement = retry_failed_schedule_run(failed_run, actor=self.user, new_due_on=timezone.localdate())
        failed_run.refresh_from_db()

        self.assertNotEqual(failed_run.pk, replacement.pk)
        self.assertEqual(replacement.run_payload["retry_of_schedule_run_id"], str(failed_run.pk))
        self.assertEqual(failed_run.run_payload["retried_by_schedule_run_id"], str(replacement.pk))
        self.assertEqual(replacement.status, PaymentScheduleRun.Status.SCHEDULED)

    def test_operational_metrics_include_conflicts_and_superseded_runs(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Streaming",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="30.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 3),
        )
        first_run = PaymentScheduleRun.objects.get(template=template)
        update_payment_template(template, next_run_at=_aware_dt(2026, 5, 4))
        first_run.refresh_from_db()

        conflict_template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Credito",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="150.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 6),
        )
        conflict_run = PaymentScheduleRun.objects.get(template=conflict_template)
        conflict_run = mark_schedule_run_paid(conflict_run, actor=self.user, paid_outside_vexxo=True, notes="Pago manual")
        intent = PaymentIntent.objects.create(
            owner=self.user,
            account=self.account,
            category=self.category,
            amount="150.00",
            currency="COP",
            provider="sandbox",
            payment_type=PaymentIntent.PaymentType.SCHEDULED,
            rail=PaymentIntent.Rail.OTHER,
            idempotency_key="metrics-conflict-intent",
            status=PaymentIntent.Status.SUCCEEDED,
        )
        conflict_run.payment_intent = intent
        conflict_run.save(update_fields=["payment_intent", "updated_at"])

        metrics = get_schedule_run_operational_metrics(owner=self.user)

        self.assertGreaterEqual(metrics["superseded_cancellations"], 1)
        self.assertGreaterEqual(metrics["conflicts_manual_vs_intent"], 1)

    def test_usage_projection_counts_only_active_modern_templates(self):
        create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Streaming moderno",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="35.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 20),
        )
        create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Template inactivo",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="15.00",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=False,
        )

        snapshot = compute_user_usage_snapshot_from_oltp(self.user)

        self.assertEqual(snapshot["scheduled_payments_active_count"], 1)

    def test_modern_run_materialization_preserves_debt_and_installment(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            debt=self.debt,
            installment=self.installment,
            name="Cuota 1",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="120.00",
            cadence=PaymentTemplate.Cadence.ONCE,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 9),
        )
        run = PaymentScheduleRun.objects.get(template=template)

        run = mark_schedule_run_paid(run, actor=self.user, paid_outside_vexxo=True)
        tx = run.materialized_transaction

        self.assertEqual(tx.debt_id, self.debt.id)
        self.assertEqual(tx.installment_id, self.installment.id)

    def test_payment_intent_materialization_preserves_debt_and_installment(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            debt=self.debt,
            installment=self.installment,
            name="Cuota PSP",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="120.00",
            cadence=PaymentTemplate.Cadence.ONCE,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 9),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        intent = create_payment_intent_from_schedule_run(run, provider="sandbox", rail="other")

        tx = materialize_transaction_from_payment_intent(intent)

        self.assertEqual(tx.debt_id, self.debt.id)
        self.assertEqual(tx.installment_id, self.installment.id)

    def test_generate_scheduled_payment_alerts_reads_modern_runs(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Servicio moderno",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="45.00",
            cadence=PaymentTemplate.Cadence.ONCE,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 10),
        )
        PaymentScheduleRun.objects.filter(template=template).update(due_on=timezone.localdate() + timezone.timedelta(days=1))

        created = generate_scheduled_payment_alerts(days_ahead=3)

        self.assertGreaterEqual(created, 1)
        alert = Alert.objects.filter(owner=self.user, type="scheduled_payment_due").last()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.payload.get("payment_template_id"), template.id)

    def test_legacy_scheduled_payments_api_is_absent(self):
        client = APIClient()
        client.force_authenticate(user=self.user)

        list_response = client.get("/api/finance/transactions/scheduled-payments/")
        self.assertEqual(list_response.status_code, 404)

        response = client.post(
            "/api/finance/transactions/scheduled-payments/",
            {
                "name": "Legacy write blocked",
                "amount": "20.00",
                "due_date": "2026-05-20",
                "account": self.account.id,
                "category": self.category.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
