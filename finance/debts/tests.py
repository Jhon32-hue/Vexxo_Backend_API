from __future__ import annotations

from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from finance.accounts.models import Account
from finance.categories.models import Category
from finance.debts.models import Debt, DebtInstallment
from finance.debts.services import apply_payment_to_debt, generate_installments_for_debt
from payments.scheduled_payments.models import PaymentTemplate
from payments.scheduled_payments.services import create_payment_template

User = get_user_model()


def _aware_dt(year, month, day, hour=9, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute), timezone.get_current_timezone())


@override_settings(DOMAIN_EVENTS_LOCAL_AUTOPUBLISH_ENABLED=False)
class DebtModernScheduledPaymentsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="debt-owner",
            email="debt-owner@example.com",
            password="secret123A",
        )
        self.account = Account.objects.create(owner=self.user, name="Cuenta deuda")
        self.category = Category.objects.create(owner=self.user, name="Deudas", type="expense")

    def test_generate_installments_is_idempotent(self):
        debt = Debt.objects.create(
            owner=self.user,
            name="Credito consumo",
            principal="1200.00",
            currency="COP",
            start_date=timezone.localdate(),
            total_installments=3,
            frequency="monthly",
        )

        # El post_save de Debt ya genera cuotas al crear la deuda. La
        # idempotencia real aqui es verificar que reintentos manuales no
        # dupliquen las existentes.
        self.assertEqual(DebtInstallment.objects.filter(debt=debt).count(), 3)

        created_first = generate_installments_for_debt(debt)
        created_second = generate_installments_for_debt(debt)

        self.assertEqual(created_first, 0)
        self.assertEqual(created_second, 0)
        self.assertEqual(DebtInstallment.objects.filter(debt=debt).count(), 3)

    def test_installment_can_link_to_modern_payment_template(self):
        debt = Debt.objects.create(
            owner=self.user,
            name="Credito libre inversion",
            principal="1200.00",
            currency="COP",
            start_date=timezone.localdate(),
        )
        installment = DebtInstallment.objects.create(
            owner=self.user,
            debt=debt,
            number=1,
            due_date=timezone.localdate(),
            amount_due="120.00",
        )

        template = create_payment_template(
            owner=self.user,
            account=self.account,
            category=self.category,
            debt=debt,
            installment=installment,
            name="Cuota 1",
            payment_type=PaymentTemplate.PaymentType.BILL,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount="120.00",
            cadence=PaymentTemplate.Cadence.ONCE,
            is_active=True,
            next_run_at=_aware_dt(2026, 5, 12),
        )
        installment.payment_template = template
        installment.save(update_fields=["payment_template", "updated_at"])
        installment.refresh_from_db()

        self.assertEqual(installment.payment_template_id, template.id)
        self.assertEqual(template.debt_id, debt.id)
        self.assertEqual(template.installment_id, installment.id)

    def test_apply_payment_to_debt_updates_installment_and_debt_status(self):
        debt = Debt.objects.create(
            owner=self.user,
            name="Credito vehiculo",
            principal="500.00",
            currency="COP",
            start_date=timezone.localdate(),
        )
        installment = DebtInstallment.objects.create(
            owner=self.user,
            debt=debt,
            number=1,
            due_date=timezone.localdate(),
            amount_due="100.00",
        )

        apply_payment_to_debt(debt=debt, amount="100.00", pay_date=timezone.localdate(), installment=installment)
        installment.refresh_from_db()
        debt.refresh_from_db()

        self.assertEqual(str(installment.paid_amount), "100.00")
        self.assertEqual(installment.status, "paid")
        self.assertEqual(debt.status, "closed")
