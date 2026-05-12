from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from alerts.alerts.models import Alert
from finance.accounts.models import Account
from finance.categories.models import Category
from finance.transactions.Models import Transaction
from payments.scheduled_payments.models import PaymentTemplate
from social.teams.models import Membership, Team

User = get_user_model()


class BudgetApiTests(TestCase):
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
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="secret123A",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.expense_category = Category.objects.create(owner=self.user, name="Comida", type="expense")
        self.expense_category_2 = Category.objects.create(owner=self.user, name="Transporte", type="expense")
        self.partner_category = Category.objects.create(owner=self.partner, name="Salidas", type="expense")
        self.income_category = Category.objects.create(owner=self.user, name="Salario", type="income")
        self.account = Account.objects.create(owner=self.user, name="Cuenta principal")
        self.partner_account = Account.objects.create(owner=self.partner, name="Cuenta pareja")
        self.team = Team.objects.create(owner=self.user, name="Pareja", description="Presupuesto compartido")
        Membership.objects.create(team=self.team, user=self.partner, role="accountant", is_active=True)

    def _tx(self, **overrides):
        payload = {
            "owner": self.user,
            "account": self.account,
            "category": self.expense_category,
            "type": Transaction.Type.EXPENSE,
            "status": Transaction.Status.POSTED,
            "confirmed": True,
            "affects_balance": True,
            "amount": Decimal("40.00"),
            "date": date(2026, 5, 6),
            "description": "Compra",
        }
        payload.update(overrides)
        return Transaction.objects.create(**payload)

    def _template(self, **overrides):
        payload = {
            "owner": self.user,
            "name": "Arriendo",
            "payment_type": "bill",
            "amount_mode": PaymentTemplate.AmountMode.FIXED,
            "default_amount": Decimal("70.00"),
            "category": self.expense_category,
            "account": self.account,
            "next_run_at": timezone.now().replace(year=2026, month=5, day=20, hour=10, minute=0, second=0, microsecond=0),
            "is_active": True,
        }
        payload.update(overrides)
        return PaymentTemplate.objects.create(**payload)

    def test_create_category_budget_returns_fixed_amount_and_dynamic_metrics(self):
        self._tx(amount=Decimal("40.00"))
        self._tx(amount=Decimal("90.00"), status=Transaction.Status.PENDING)
        self._tx(amount=Decimal("30.00"), confirmed=False)
        self._template(default_amount=Decimal("70.00"))

        response = self.client.post(
            "/api/finance/budgets/presupuestos-categoria/",
            {
                "month": "2026-05",
                "category": self.expense_category.pk,
                "amount": "500.00",
                "alert_thresholds": [30, 50, 70, 100],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["amount"], "500.00")
        self.assertEqual(response.data["metrics"]["actual_spent"], "40.00")
        self.assertEqual(response.data["metrics"]["committed_spent"], "70.00")
        self.assertEqual(response.data["metrics"]["projected_spent"], "110.00")
        self.assertEqual(response.data["metrics"]["remaining"], "460.00")
        self.assertEqual(response.data["metrics"]["available_after_committed"], "390.00")
        self.assertEqual(response.data["metrics"]["alert_state"], "ok")

    def test_personal_budget_excludes_shared_attributed_transactions(self):
        shared_budget = self.client.post(
            "/api/finance/budgets/presupuestos-compartidos/",
            {"team": self.team.pk, "name": "Viaje", "month": "2026-05", "amount": "300.00"},
            format="json",
        ).data
        self._tx(amount=Decimal("60.00"))
        self._tx(amount=Decimal("90.00"), budget_scope="shared", shared_budget_id=shared_budget["id"], budget_attribution_source="manual")

        response = self.client.post(
            "/api/finance/budgets/presupuestos-categoria/",
            {"month": "2026-05", "category": self.expense_category.pk, "amount": "200.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["metrics"]["actual_spent"], "60.00")

    def test_category_budget_rejects_income_category(self):
        response = self.client.post(
            "/api/finance/budgets/presupuestos-categoria/",
            {"month": "2026-05", "category": self.income_category.pk, "amount": "100.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data)

    def test_owner_scoping_hides_personal_budgets_from_other_users(self):
        self.client.post(
            "/api/finance/budgets/presupuestos-categoria/",
            {"month": "2026-05", "category": self.expense_category.pk, "amount": "100.00"},
            format="json",
        )

        other_client = APIClient()
        other_client.force_authenticate(user=self.other_user)
        response = other_client.get("/api/finance/budgets/presupuestos-categoria/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_merge_and_replace_category_budget_period(self):
        merge_response = self.client.post(
            "/api/finance/budgets/presupuestos-categoria/merge-period/",
            {
                "month": "2026-05",
                "items": [
                    {"category": self.expense_category.pk, "amount": "100.00", "alert_thresholds": [50, 100]},
                    {"category": self.expense_category_2.pk, "amount": "50.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(merge_response.status_code, 200)
        self.assertEqual(merge_response.data["summary"]["count"], 2)

        replace_response = self.client.post(
            "/api/finance/budgets/presupuestos-categoria/replace-period/",
            {
                "month": "2026-05",
                "items": [
                    {"category": self.expense_category.pk, "amount": "120.00", "alert_thresholds": [30, 70, 100]},
                ],
            },
            format="json",
        )
        self.assertEqual(replace_response.status_code, 200)
        self.assertEqual(replace_response.data["summary"]["count"], 1)
        self.assertEqual(replace_response.data["results"][0]["amount"], "120.00")
        self.assertEqual(replace_response.data["results"][0]["alert_thresholds"], [30, 70, 100])

    def test_threshold_alerts_follow_manual_thresholds_and_resolve_on_delete(self):
        self._tx(amount=Decimal("85.00"))
        create_response = self.client.post(
            "/api/finance/budgets/presupuestos-categoria/",
            {
                "month": "2026-05",
                "category": self.expense_category.pk,
                "amount": "100.00",
                "alert_thresholds": [30, 50, 70, 100],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)

        thresholds = sorted(
            Alert.objects.filter(owner=self.user, source="finance.budgets.monitoring", is_active=True)
            .values_list("payload__threshold_percent", flat=True)
        )
        self.assertEqual(thresholds, [30, 50, 70])

        budget_id = create_response.data["id"]
        delete_response = self.client.delete(f"/api/finance/budgets/presupuestos-categoria/{budget_id}/")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Alert.objects.filter(owner=self.user, source="finance.budgets.monitoring", is_active=True).exists())

    def test_shared_budget_supports_partner_transactions_and_templates(self):
        partner_tx = Transaction.objects.create(
            owner=self.partner,
            account=self.partner_account,
            category=self.partner_category,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.POSTED,
            confirmed=True,
            affects_balance=True,
            amount=Decimal("120.00"),
            date=date(2026, 5, 8),
            description="Cena grupo",
        )
        partner_template = PaymentTemplate.objects.create(
            owner=self.partner,
            name="Reserva salida",
            payment_type="other",
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount=Decimal("80.00"),
            category=self.partner_category,
            account=self.partner_account,
            next_run_at=timezone.now().replace(year=2026, month=5, day=22, hour=9, minute=0, second=0, microsecond=0),
            is_active=True,
        )

        create_response = self.client.post(
            "/api/finance/budgets/presupuestos-compartidos/",
            {
                "team": self.team.pk,
                "name": "Salida mayo",
                "month": "2026-05",
                "amount": "500.00",
                "alert_thresholds": [50, 100],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        budget_id = create_response.data["id"]

        link_tx_response = self.client.post(
            f"/api/finance/budgets/presupuestos-compartidos/{budget_id}/link-transaction/",
            {"transaction_id": partner_tx.pk},
            format="json",
        )
        self.assertEqual(link_tx_response.status_code, 200)
        self.assertEqual(link_tx_response.data["metrics"]["actual_spent"], "120.00")

        link_template_response = self.client.post(
            f"/api/finance/budgets/presupuestos-compartidos/{budget_id}/link-template/",
            {"payment_template_id": partner_template.pk},
            format="json",
        )
        self.assertEqual(link_template_response.status_code, 200)
        self.assertEqual(link_template_response.data["metrics"]["committed_spent"], "80.00")
        self.assertEqual(link_template_response.data["metrics"]["projected_spent"], "200.00")
        self.assertEqual(link_template_response.data["linked_transactions_count"], 1)
        self.assertEqual(link_template_response.data["linked_templates_count"], 1)

    def test_shared_budget_counts_attributed_transaction_and_template_without_manual_link(self):
        create_response = self.client.post(
            "/api/finance/budgets/presupuestos-compartidos/",
            {
                "team": self.team.pk,
                "name": "Cartagena",
                "month": "2026-05",
                "amount": "500.00",
            },
            format="json",
        )
        budget_id = create_response.data["id"]
        Transaction.objects.create(
            owner=self.partner,
            account=self.partner_account,
            category=self.partner_category,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.POSTED,
            confirmed=True,
            affects_balance=True,
            amount=Decimal("110.00"),
            date=date(2026, 5, 12),
            description="Hotel",
            budget_scope="shared",
            shared_budget_id=budget_id,
            budget_attribution_source="manual",
        )
        PaymentTemplate.objects.create(
            owner=self.partner,
            name="Reserva paseo",
            payment_type="other",
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount=Decimal("55.00"),
            category=self.partner_category,
            account=self.partner_account,
            next_run_at=timezone.now().replace(year=2026, month=5, day=23, hour=9, minute=0, second=0, microsecond=0),
            is_active=True,
            budget_scope="shared",
            shared_budget_id=budget_id,
            budget_attribution_source="manual",
        )

        response = self.client.get(f"/api/finance/budgets/presupuestos-compartidos/{budget_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["metrics"]["actual_spent"], "110.00")
        self.assertEqual(response.data["metrics"]["committed_spent"], "55.00")

    def test_shared_budget_is_visible_to_active_member_and_hidden_from_outsider(self):
        create_response = self.client.post(
            "/api/finance/budgets/presupuestos-compartidos/",
            {
                "team": self.team.pk,
                "name": "Plan pareja",
                "month": "2026-05",
                "amount": "300.00",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        budget_id = create_response.data["id"]

        partner_client = APIClient()
        partner_client.force_authenticate(user=self.partner)
        partner_response = partner_client.get(f"/api/finance/budgets/presupuestos-compartidos/{budget_id}/")
        self.assertEqual(partner_response.status_code, 200)

        outsider_client = APIClient()
        outsider_client.force_authenticate(user=self.other_user)
        outsider_response = outsider_client.get(f"/api/finance/budgets/presupuestos-compartidos/{budget_id}/")
        self.assertEqual(outsider_response.status_code, 403)

    def test_reports_budget_monthly_summary_view_uses_budget_service(self):
        self._tx(amount=Decimal("45.00"))
        shared_tx = Transaction.objects.create(
            owner=self.partner,
            account=self.partner_account,
            category=self.partner_category,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.POSTED,
            confirmed=True,
            affects_balance=True,
            amount=Decimal("65.00"),
            date=date(2026, 5, 10),
            description="Salida",
        )
        self.client.post(
            "/api/finance/budgets/presupuestos-categoria/",
            {"month": "2026-05", "category": self.expense_category.pk, "amount": "100.00"},
            format="json",
        )
        shared_response = self.client.post(
            "/api/finance/budgets/presupuestos-compartidos/",
            {"team": self.team.pk, "name": "Plan salida", "month": "2026-05", "amount": "200.00"},
            format="json",
        )
        budget_id = shared_response.data["id"]
        self.client.post(
            f"/api/finance/budgets/presupuestos-compartidos/{budget_id}/link-transaction/",
            {"transaction_id": shared_tx.pk},
            format="json",
        )

        response = self.client.get("/api/reports/reportes/presupuestos-mensuales?month=2026-05")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["month"], "2026-05")
        self.assertIn("personal_category_summary", response.data)
        self.assertIn("shared_summary", response.data)
        self.assertEqual(response.data["personal_category_summary"]["total_actual"], "45.00")
        self.assertEqual(response.data["shared_summary"]["total_actual"], "65.00")
