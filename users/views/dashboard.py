from rest_framework import views, permissions
from rest_framework.response import Response
from django.db.models import Sum, Q
from datetime import date, timedelta

from accounts.models.account import Account
from transactions.Models.transacciones import Transaction  
from debts.models import Debt, DebtInstallment
from goals.models import Goal
from alerts.models import Alert
from teams.models import Membership

class UserDashboardView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # --- Finanzas ---
        accounts = Account.objects.filter(owner=user)
        total_balance = accounts.aggregate(total=Sum("balance"))["total"] or 0
        month_start = date.today().replace(day=1)
        expenses_month = Transaction.objects.filter(
            owner=user, type="expense", date__gte=month_start
        ).aggregate(total=Sum("amount"))["total"] or 0
        income_month = Transaction.objects.filter(
            owner=user, type="income", date__gte=month_start
        ).aggregate(total=Sum("amount"))["total"] or 0

        # --- Deudas y cuotas ---
        active_debts = Debt.objects.filter(owner=user, status="active")
        next_installments = DebtInstallment.objects.filter(
            debt__owner=user, due_date__gte=date.today()
        ).order_by("due_date")[:3]

        # --- Metas ---
        goals = Goal.objects.filter(owner=user)
        goals_data = [
            {"name": g.name, "progress": float(g.progress or 0), "target": float(g.target_amount)}
            for g in goals
        ]

        # --- Cuentas compartidas ---
        teams = Membership.objects.filter(user=user).select_related("team")
        team_data = [{"team": m.team.name, "role": m.role} for m in teams]

        # --- Alertas y tips ---
        unread_alerts = Alert.objects.filter(owner=user, read_at__isnull=True).count()
        latest_alerts = Alert.objects.filter(owner=user).order_by("-created_at")[:3]

        # --- Recompensas (placeholder) ---
        rewards = [
            {"title": "Primer registro de gasto", "points": 10, "achieved": True},
            {"title": "Meta creada", "points": 5, "achieved": len(goals) > 0},
        ]

        return Response({
            "user": user.username,
            "preferred_currency": user.preferred_currency,
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
                for t in Transaction.objects.filter(owner=user).order_by("-date")[:5]
            ],
            "next_installments": [
                {"debt": inst.debt.name, "due_date": inst.due_date, "amount_due": float(inst.amount_due)}
                for inst in next_installments
            ],
            "goals": goals_data,
            "teams": team_data,
            "alerts": [
                {
                    "title": a.payload.get("title"),
                    "message": a.payload.get("message"),
                    "type": a.type,
                } for a in latest_alerts
            ],
            "rewards": rewards,
        })
