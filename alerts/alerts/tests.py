from __future__ import annotations

from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from alerts.alerts.models.alerts import AlertType
from alerts.alerts.services import generate_scheduled_payment_alerts
from finance.accounts.models import Account
from finance.categories.models import Category
from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate
from payments.scheduled_payments.services import create_payment_template

User = get_user_model()


def _aware_dt(year, month, day, hour=9, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute), timezone.get_current_timezone())


@override_settings(DOMAIN_EVENTS_LOCAL_AUTOPUBLISH_ENABLED=False)
class ScheduledPaymentAlertsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alerts-owner",
            email="alerts-owner@example.com",
            password="secret123A",
        )
        self.account = Account.objects.create(owner=self.user, name="Cuenta alertas")
        self.category = Category.objects.create(owner=self.user, name="Servicios", type="expense")

    def test_generate_scheduled_payment_alerts_reads_modern_schedule_runs(self):
        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            name="Internet hogar",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="89.90",
            cadence=PaymentTemplate.Cadence.MONTHLY,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 12),
        )
        run = PaymentScheduleRun.objects.get(template=template)
        run.due_on = timezone.localdate()
        run.status = PaymentScheduleRun.Status.DUE
        run.save(update_fields=["due_on", "status", "updated_at"])

        created = generate_scheduled_payment_alerts(days_ahead=0)

        self.assertEqual(created, 1)
        alert = self.user.alerts.latest("created_at")
        self.assertEqual(alert.type, AlertType.SCHEDULED_PAYMENT_DUE)
        self.assertEqual(str(alert.payload["payment_schedule_run_id"]), str(run.pk))
        self.assertEqual(str(alert.payload["payment_template_id"]), str(template.pk))
        self.assertNotIn("scheduled_payment_id", alert.payload)
