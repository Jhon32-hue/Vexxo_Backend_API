from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from finance.accounts.models import Account
from finance.categories.models import Category
from finance.debts.models import Debt, DebtDomainEventOutbox, DebtInstallment, DebtRestructuring
from finance.debts.services import (
    apply_payment_to_debt,
    create_debt,
    generate_installments_for_debt,
    refresh_overdue_installments,
)
from finance.vendors.models import Vendor
from payments.scheduled_payments.models import PaymentTemplate
from payments.scheduled_payments.services import create_payment_template

User = get_user_model()


def _aware_dt(year, month, day, hour=9, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute), timezone.get_current_timezone())


class DebtApiIsolationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="debt-api-owner",
            email="debt-api-owner@example.com",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="debt-api-other",
            email="debt-api-other@example.com",
            password="test-password",
        )
        self.vendor = Vendor.objects.create(owner=self.user, name="Banco propio")
        self.other_vendor = Vendor.objects.create(owner=self.other_user, name="Banco ajeno")
        self.debt = create_debt(
            owner=self.user,
            vendor=self.vendor,
            name="Deuda propia",
            principal="1200.00",
            start_date=timezone.localdate(),
            total_installments=2,
        )
        self.other_debt = create_debt(
            owner=self.other_user,
            vendor=self.other_vendor,
            name="Deuda ajena",
            principal="3000.00",
            start_date=timezone.localdate(),
            total_installments=2,
        )
        self.client.force_authenticate(self.user)

    def test_debts_and_installments_are_scoped_to_authenticated_owner(self):
        debts = self.client.get("/api/finance/debts/deudas/")
        installments = self.client.get("/api/finance/debts/cuotas-deuda/")

        self.assertEqual(debts.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in debts.data], [self.debt.id])
        self.assertEqual(installments.status_code, status.HTTP_200_OK)
        self.assertTrue(installments.data)
        self.assertEqual({item["owner"] for item in installments.data}, {self.user.id})
        hidden = self.client.get(f"/api/finance/debts/deudas/{self.other_debt.id}/")
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_assigns_owner_and_rejects_foreign_vendor(self):
        payload = {
            "name": "Deuda nueva",
            "principal": "900.00",
            "start_date": str(timezone.localdate()),
            "total_installments": 3,
            "vendor": self.other_vendor.id,
            "owner": self.other_user.id,
        }
        rejected = self.client.post("/api/finance/debts/deudas/", payload, format="json")
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vendor", rejected.data)

        payload["vendor"] = self.vendor.id
        created = self.client.post("/api/finance/debts/deudas/", payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        debt = Debt.objects.get(pk=created.data["id"])
        self.assertEqual(debt.owner, self.user)
        self.assertEqual(debt.installments.count(), 3)

    def test_installment_create_rejects_foreign_debt(self):
        response = self.client.post(
            "/api/finance/debts/cuotas-deuda/",
            {
                "debt": self.other_debt.id,
                "number": 99,
                "due_date": str(timezone.localdate()),
                "amount_due": "100.00",
                "owner": self.other_user.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("debt", response.data)

    def test_installment_cannot_be_moved_to_another_debt(self):
        second_debt = create_debt(
            owner=self.user,
            name="Otra deuda propia",
            principal="800.00",
            start_date=timezone.localdate(),
            total_installments=1,
        )
        installment = self.debt.installments.first()

        response = self.client.patch(
            f"/api/finance/debts/cuotas-deuda/{installment.id}/",
            {"debt": second_debt.id, "number": 99},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("debt", response.data)
        installment.refresh_from_db()
        self.assertEqual(installment.debt_id, self.debt.id)

    def test_restructure_preserves_paid_history_and_replaces_only_pending_schedule(self):
        paid = self.debt.installments.order_by("number").first()
        apply_payment_to_debt(
            debt=self.debt,
            amount=paid.amount_due,
            pay_date=timezone.localdate(),
            installment=paid,
        )
        effective = timezone.localdate() + timedelta(days=40)
        payload = {
            "effective_date": str(effective),
            "reason": "Renegotiation accepted after affordability review",
            "new_terms": {
                "principal": "700.00",
                "interest_rate": "1.5000",
                "interest_type": "fixed",
                "compounding": "monthly",
                "term_months": 2,
                "frequency": "monthly",
            },
            "installments": [
                {
                    "due_date": str(effective),
                    "amount_due": "360.00",
                    "principal_component": "350.00",
                    "interest_component": "10.00",
                },
                {
                    "due_date": str(effective + timedelta(days=30)),
                    "amount_due": "360.00",
                    "principal_component": "350.00",
                    "interest_component": "10.00",
                },
            ],
        }
        url = f"/api/finance/debts/deudas/{self.debt.pk}/restructure/"
        first = self.client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="restructure-001")
        replay = self.client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="restructure-001")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(replay.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(DebtRestructuring.objects.count(), 1)
        installments = list(self.debt.installments.order_by("number"))
        self.assertEqual(len(installments), 3)
        self.assertEqual(installments[0].pk, paid.pk)
        self.assertEqual(installments[0].status, "paid")
        self.assertEqual([row.number for row in installments], [1, 2, 3])


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
        debt = create_debt(
            owner=self.user,
            name="Credito consumo",
            principal="1200.00",
            currency="COP",
            start_date=timezone.localdate(),
            total_installments=3,
            frequency="monthly",
        )

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
        self.assertIsNotNone(debt.closed_at)

    def test_direct_model_save_has_no_hidden_installment_side_effect(self):
        debt = Debt.objects.create(
            owner=self.user,
            name="Sin orquestacion oculta",
            principal="600.00",
            currency="COP",
            start_date=timezone.localdate(),
            total_installments=2,
        )

        self.assertFalse(debt.installments.exists())

    def test_refresh_overdue_is_explicit_and_emits_outbox(self):
        debt = create_debt(
            owner=self.user,
            name="Credito vencido",
            principal="100.00",
            currency="COP",
            start_date=timezone.localdate() - timedelta(days=30),
            total_installments=1,
        )
        DebtDomainEventOutbox.objects.all().delete()

        updated = refresh_overdue_installments()

        debt.refresh_from_db()
        installment = debt.installments.get()
        self.assertEqual(updated, 1)
        self.assertEqual(installment.status, "overdue")
        self.assertEqual(debt.status, "overdue")
        self.assertTrue(
            DebtDomainEventOutbox.objects.filter(event_type="debts.overdue.refreshed.v1").exists()
        )
