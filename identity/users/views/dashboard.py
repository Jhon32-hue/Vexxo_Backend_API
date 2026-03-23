# users/views/dashboard.py
from datetime import date

from django.db.models import Sum
from rest_framework import views, permissions
from rest_framework.response import Response

from finance.accounts.models.account import Account
from finance.transactions.Models.transacciones import Transaction
from finance.debts.models import Debt, DebtInstallment
from planning.goals.models import Goal
from alerts.alerts.models import Alert
from social.teams.models import Membership


class UserDashboardView(views.APIView):
    """
    Endpoint para poblar el dashboard principal de Mindwallet
    (Resumen 360, próximos pagos, equipos, alertas, etc.).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        today = date.today()
        month_start = today.replace(day=1)

        # --- Finanzas ---
        accounts = Account.objects.filter(owner=user, is_active=True)
        total_balance = accounts.aggregate(total=Sum("balance"))["total"] or 0

        expenses_month = (
            Transaction.objects.filter(
                owner=user, type="expense", date__gte=month_start
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        income_month = (
            Transaction.objects.filter(
                owner=user, type="income", date__gte=month_start
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )

        # --- Deudas y cuotas ---
        active_debts = Debt.objects.filter(owner=user, status="active")
        next_installments = (
            DebtInstallment.objects.filter(
                debt__owner=user, due_date__gte=today
            )
            .order_by("due_date")[:3]
        )

        # --- Metas ---
        goals = Goal.objects.filter(owner=user)
        goals_data = [
            {
                "name": g.name,
                "progress": float(getattr(g, "progress", 0) or 0),
                "target": float(g.target_amount),
            }
            for g in goals
        ]

        # --- Equipos / cuentas compartidas ---
        teams = Membership.objects.filter(user=user).select_related("team")
        team_data = [{"team": m.team.name, "role": m.role} for m in teams]

        # --- Alertas ---
        unread_alerts = Alert.objects.filter(owner=user, read_at__isnull=True).count()
        latest_alerts = Alert.objects.filter(owner=user).order_by("-created_at")[:3]

        # --- Recompensas (placeholder gamificación) ---
        rewards = [
            {"title": "Primer registro de gasto", "points": 10, "achieved": True},
            {"title": "Meta creada", "points": 5, "achieved": len(goals) > 0},
        ]

        # --- Info de plan / límites (para UI) ---
        plan_config = user.get_plan_config()

        return Response(
            {
                "user": {
                    "username": user.username,
                    "full_name": user.full_name(),
                    "preferred_currency": user.preferred_currency,
                    "plan": user.plan,
                },
                "summary": {
                    "total_balance": float(total_balance),
                    "monthly_expenses": float(expenses_month),
                    "monthly_income": float(income_month),
                    "active_debts": active_debts.count(),
                    "unread_alerts": unread_alerts,
                },
                "recent_transactions": [
                    {
                        "id": t.id,
                        "type": t.type,
                        "amount": float(t.amount),
                        "category": getattr(t.category, "name", None),
                        "date": t.date,
                    }
                    for t in Transaction.objects.filter(owner=user)
                    .order_by("-date")[:5]
                ],
                "next_installments": [
                    {
                        "debt": inst.debt.name,
                        "due_date": inst.due_date,
                        "amount_due": float(inst.amount_due),
                    }
                    for inst in next_installments
                ],
                "goals": goals_data,
                "teams": team_data,
                "alerts": [
                    {
                        "title": a.payload.get("title"),
                        "message": a.payload.get("message"),
                        "type": a.type,
                    }
                    for a in latest_alerts
                ],
                "rewards": rewards,
                "plan_limits": plan_config,
            }
        )
