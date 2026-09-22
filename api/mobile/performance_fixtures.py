from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from alerts.alerts.models.alerts import Alert
from finance.accounts.models import Account
from finance.budgets.Models.budget import Budget
from finance.budgets.Models.shared_budget import SharedBudget
from finance.categories.models import Category
from finance.transactions.Models.transacciones import Transaction
from notifications.deliveries.models import NotificationDelivery, NotificationStatus
from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate
from planning.goals.models import Goal
from social.teams.models import Team


@dataclass(frozen=True)
class MobileFixtureScale:
    accounts: int
    categories: int
    transactions: int
    budgets: int
    shared_budgets: int
    payment_templates: int
    payment_runs: int
    goals: int
    notifications: int
    alerts: int
    teams: int


MOBILE_FIXTURE_SCALES = {
    "small": MobileFixtureScale(2, 6, 20, 4, 1, 3, 3, 3, 5, 4, 1),
    "medium": MobileFixtureScale(5, 15, 250, 12, 3, 15, 30, 15, 40, 30, 3),
    "large": MobileFixtureScale(12, 30, 2000, 24, 10, 60, 120, 60, 200, 150, 10),
}


def build_mobile_performance_fixture(*, profile: str):
    try:
        scale = MOBILE_FIXTURE_SCALES[profile]
    except KeyError as exc:
        raise ValueError(f"Perfil mobile desconocido: {profile}") from exc

    now = timezone.now()
    today = timezone.localdate()
    month = today.strftime("%Y-%m")
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username=f"mobile-perf-{profile}",
        email=f"mobile-perf-{profile}@vexxo.local",
        password=None,
        status="active",
        onboarding_completed=True,
    )

    accounts = Account.objects.bulk_create(
        [
            Account(
                owner=user,
                name=f"Cuenta {index:03d}",
                display_order=index,
                balance=Decimal("1000000.00") + index,
                is_primary=index == 0,
            )
            for index in range(scale.accounts)
        ]
    )
    categories = Category.objects.bulk_create(
        [
            Category(
                owner=user,
                name=f"Categoria {index:03d}",
                type="expense" if index % 4 else "income",
            )
            for index in range(scale.categories)
        ]
    )
    Transaction.objects.bulk_create(
        [
            Transaction(
                owner=user,
                account=accounts[index % len(accounts)],
                category=categories[index % len(categories)],
                type="income" if index % 5 == 0 else "expense",
                amount=Decimal("10000.00") + index,
                date=today - timedelta(days=index % 45),
                description=f"Movimiento rendimiento {index:05d}",
            )
            for index in range(scale.transactions)
        ],
        batch_size=500,
    )
    Budget.objects.bulk_create(
        [
            Budget(
                owner=user,
                month=month,
                category=categories[index % len(categories)],
                amount=Decimal("500000.00") + index,
            )
            for index in range(min(scale.budgets, len(categories)))
        ]
    )

    teams = Team.objects.bulk_create(
        [Team(owner=user, name=f"Equipo rendimiento {index:03d}", is_personal=False) for index in range(scale.teams)]
    )
    SharedBudget.objects.bulk_create(
        [
            SharedBudget(
                owner=user,
                team=teams[index % len(teams)],
                name=f"Compartido {index:03d}",
                month=month,
                amount=Decimal("750000.00") + index,
            )
            for index in range(scale.shared_budgets)
        ]
    )

    templates = PaymentTemplate.objects.bulk_create(
        [
            PaymentTemplate(
                owner=user,
                account=accounts[index % len(accounts)],
                category=categories[index % len(categories)],
                name=f"Pago programado {index:03d}",
                default_amount=Decimal("50000.00") + index,
                next_run_at=now + timedelta(days=index % 30),
            )
            for index in range(scale.payment_templates)
        ]
    )
    PaymentScheduleRun.objects.bulk_create(
        [
            PaymentScheduleRun(
                owner=user,
                template=templates[index % len(templates)],
                scheduled_for=now + timedelta(days=index % 30),
                due_on=today + timedelta(days=index % 30),
                expected_amount=Decimal("50000.00") + index,
                idempotency_key=f"mobile-perf-{profile}-run-{index}",
            )
            for index in range(scale.payment_runs)
        ]
    )
    Goal.objects.bulk_create(
        [
            Goal(
                owner=user,
                account=accounts[index % len(accounts)],
                name=f"Meta rendimiento {index:03d}",
                target_amount=Decimal("1000000.00") + index,
                target_date=today + timedelta(days=90 + index),
                progress=Decimal("10000.00") + index,
            )
            for index in range(scale.goals)
        ]
    )
    NotificationDelivery.objects.bulk_create(
        [
            NotificationDelivery(
                owner=user,
                status=NotificationStatus.READ if index % 3 == 0 else NotificationStatus.DELIVERED,
                event_type="performance.fixture",
                source="api.mobile.performance_fixtures",
                title=f"Notificacion {index:03d}",
                message="Fixture local de rendimiento",
                dedupe_key=f"mobile-perf-{profile}-notification-{index}",
            )
            for index in range(scale.notifications)
        ]
    )
    Alert.objects.bulk_create(
        [
            Alert(
                owner=user,
                type="generic",
                severity="critical" if index % 10 == 0 else "info",
                status="new" if index % 2 == 0 else "ack",
                title=f"Alerta {index:03d}",
                message="Fixture local de rendimiento",
                is_active=index % 5 != 0,
            )
            for index in range(scale.alerts)
        ]
    )
    return user, asdict(scale)
