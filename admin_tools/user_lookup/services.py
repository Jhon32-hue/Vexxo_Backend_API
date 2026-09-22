from django.db.models import Count, QuerySet

from alerts.alerts.models import Alert
from finance.accounts.models import Account
from finance.budgets.Models import Budget, SharedBudget
from finance.debts.models import Debt
from finance.transactions.Models.transacciones import Transaction
from identity.consents.models import UserConsent
from identity.devices.models import UserDevice
from identity.sessions.models import UserSession
from notifications.deliveries.models import NotificationDelivery
from payments.payment_intents.models import PaymentIntent
from planning.goals.models import Goal, GoalContribution


def _counts_by(queryset: QuerySet, field: str) -> dict[str, int]:
    return {
        str(row[field]): row["total"]
        for row in queryset.values(field).annotate(total=Count("id")).order_by()
    }


def serialize_user_summary(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "plan": user.effective_plan,
        "status": user.status,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "onboarding_completed": user.onboarding_completed,
        "created_at": user.created_at,
        "last_seen": user.last_seen,
    }


def build_user_support_overview(user) -> dict:
    accounts = Account.objects.filter(owner=user)
    transactions = Transaction.objects.filter(owner=user)
    debts = Debt.objects.filter(owner=user)
    payment_intents = PaymentIntent.objects.filter(owner=user)
    alerts = Alert.objects.filter(owner=user)
    notifications = NotificationDelivery.objects.filter(owner=user)
    devices = UserDevice.objects.filter(user=user)
    sessions = UserSession.objects.filter(user=user)
    consents = UserConsent.objects.filter(user=user)

    return {
        "identity": serialize_user_summary(user),
        "security": {
            "devices": {"total": devices.count(), "active": devices.filter(is_active=True).count()},
            "sessions": {"total": sessions.count(), "by_status": _counts_by(sessions, "status")},
            "consents": {"total": consents.count(), "by_status": _counts_by(consents, "status")},
        },
        "finance": {
            "accounts": {"total": accounts.count(), "by_status": _counts_by(accounts, "status")},
            "transactions": {
                "total": transactions.count(),
                "by_status": _counts_by(transactions, "status"),
                "by_type": _counts_by(transactions, "type"),
            },
            "budgets": Budget.objects.filter(owner=user).count(),
            "shared_budgets": SharedBudget.objects.filter(owner=user).count(),
            "debts": {"total": debts.count(), "by_status": _counts_by(debts, "status")},
            "goals": {
                "total": Goal.objects.filter(owner=user).count(),
                "by_status": _counts_by(Goal.objects.filter(owner=user), "status"),
                "contributions": GoalContribution.objects.filter(owner=user).count(),
                "reversed_contributions": GoalContribution.objects.filter(
                    owner=user,
                    reversed_at__isnull=False,
                ).count(),
            },
        },
        "operations": {
            "payment_intents": {
                "total": payment_intents.count(),
                "by_status": _counts_by(payment_intents, "status"),
            },
            "alerts": {
                "total": alerts.count(),
                "active": alerts.filter(is_active=True).count(),
                "unread": alerts.filter(read_at__isnull=True).count(),
            },
            "notifications": {
                "total": notifications.count(),
                "unread": notifications.filter(read_at__isnull=True).count(),
            },
        },
    }
