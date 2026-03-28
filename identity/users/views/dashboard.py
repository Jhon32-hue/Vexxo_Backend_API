"""
Dashboard principal del usuario.

Descripcion general:
- compone una vista 360 del usuario mezclando identidad, cuentas, deudas,
  alertas, metas y actividad reciente

Analisis detallado:
- el dashboard ya no debe recalcular todo el universo financiero desde cero si
  `accounts` ya provee snapshots y metricas derivadas
- por eso este endpoint reutiliza `AccountOwnerMetrics`,
  `AccountPortfolioSnapshot` y `AccountRiskSnapshot` cuando existen, con
  fallback de refresco si aun no se han materializado
"""

from __future__ import annotations

from datetime import date
import logging

from django.db.models import Sum
from rest_framework import permissions, views
from rest_framework.response import Response

from alerts.alerts.models.alerts import Alert
from finance.accounts.models import Account, AccountOwnerMetrics, AccountPortfolioSnapshot, AccountRiskSnapshot
from finance.accounts.models.account import AccountStatus
from finance.accounts.services.intelligence_dispatch_service import (
    account_intelligence_local_fallback_allowed,
    enqueue_account_intelligence_refresh_task,
    get_account_intelligence_projection_status,
)
from finance.accounts.services.intelligence_health_service import get_account_intelligence_operational_health
from finance.accounts.services.intelligence_service import refresh_account_intelligence_for_user
from finance.debts.models import Debt, DebtInstallment
from finance.transactions.Models.transacciones import Transaction
from planning.goals.models import Goal
from social.teams.models.membership import Membership

logger = logging.getLogger(__name__)


class UserDashboardView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _ensure_account_snapshots(self, user):
        owner_metrics = AccountOwnerMetrics.objects.filter(owner=user).first()
        portfolio = AccountPortfolioSnapshot.objects.filter(owner=user).first()
        risk = AccountRiskSnapshot.objects.filter(owner=user).first()

        if owner_metrics and portfolio and risk:
            return owner_metrics, portfolio, risk

        response = enqueue_account_intelligence_refresh_task(
            owner_id=user.pk,
            source="identity.users.dashboard.ensure_snapshots",
            task_name_suffix=f"dashboard-{user.pk}",
        )
        if not account_intelligence_local_fallback_allowed():
            if response is None and (owner_metrics is None or portfolio is None or risk is None):
                logger.warning(
                    "[identity.dashboard] Projection pending without async dispatch user_id=%s",
                    user.pk,
                )
            return owner_metrics, portfolio, risk
        result = refresh_account_intelligence_for_user(user)
        if result is None:
            return None, None, None
        return (
            result["owner_metrics"],
            result["portfolio_snapshot"],
            result["risk_snapshot"],
        )

    def get(self, request):
        user = request.user
        today = date.today()
        month_start = today.replace(day=1)

        owner_metrics, portfolio, risk = self._ensure_account_snapshots(user)
        projection_status = get_account_intelligence_projection_status(owner=user)
        projection_health = get_account_intelligence_operational_health(
            owner=user,
            sync_alerts=True,
        )
        accounts_qs = Account.objects.filter(owner=user).exclude(status=AccountStatus.CLOSED)
        total_balance = (
            getattr(owner_metrics, "total_cached_balance_in_base", None)
            if owner_metrics is not None
            else accounts_qs.aggregate(total=Sum("balance"))["total"] or 0
        )

        expenses_month = (
            Transaction.objects.filter(owner=user, type="expense", date__gte=month_start).aggregate(total=Sum("amount"))["total"]
            or 0
        )
        income_month = (
            Transaction.objects.filter(owner=user, type="income", date__gte=month_start).aggregate(total=Sum("amount"))["total"]
            or 0
        )

        active_debts = Debt.objects.filter(owner=user, status="active")
        next_installments = DebtInstallment.objects.filter(debt__owner=user, due_date__gte=today).order_by("due_date")[:3]
        goals = Goal.objects.filter(owner=user)
        teams = Membership.objects.filter(user=user).select_related("team")
        unread_alerts = Alert.objects.filter(owner=user, read_at__isnull=True).count()
        latest_alerts = Alert.objects.filter(owner=user).order_by("-created_at")[:3]

        return Response(
            {
                "user": {
                    "id": str(user.pk),
                    "username": user.username,
                    "full_name": user.display_name,
                    "preferred_currency": user.preferred_currency,
                    "plan": user.plan,
                    "status": user.status,
                    "onboarding_completed": bool(user.onboarding_completed),
                },
                "summary": {
                    "total_balance": float(total_balance or 0),
                    "monthly_expenses": float(expenses_month),
                    "monthly_income": float(income_month),
                    "active_debts": active_debts.count(),
                    "unread_alerts": unread_alerts,
                },
                "accounts": {
                    "owner_metrics": {
                        "total_accounts": getattr(owner_metrics, "total_accounts", 0),
                        "active_accounts": getattr(owner_metrics, "active_accounts", 0),
                        "primary_accounts": getattr(owner_metrics, "primary_accounts", 0),
                        "shared_accounts": getattr(owner_metrics, "shared_accounts", 0),
                        "external_accounts": getattr(owner_metrics, "external_accounts", 0),
                        "currencies_count": getattr(owner_metrics, "currencies_count", 0),
                    }
                    if owner_metrics
                    else None,
                    "portfolio": {
                        "has_multi_currency_accounts": getattr(portfolio, "has_multi_currency_accounts", False),
                        "has_external_linked_accounts": getattr(portfolio, "has_external_linked_accounts", False),
                        "has_investment_exposure": getattr(portfolio, "has_investment_exposure", False),
                        "has_credit_products": getattr(portfolio, "has_credit_products", False),
                        "has_shared_financial_behavior": getattr(portfolio, "has_shared_financial_behavior", False),
                        "portfolio_complexity_score": getattr(portfolio, "portfolio_complexity_score", 0),
                        "account_diversification_score": getattr(portfolio, "account_diversification_score", 0),
                    }
                    if portfolio
                    else None,
                    "risk": {
                        "segment_label": getattr(risk, "segment_label", ""),
                        "is_credit_ready_candidate": getattr(risk, "is_credit_ready_candidate", False),
                        "portfolio_stability_score": getattr(risk, "portfolio_stability_score", 0),
                        "sync_reliability_score": getattr(risk, "sync_reliability_score", 0),
                    }
                    if risk
                    else None,
                    "projection_status": projection_status,
                    "projection_health": projection_health,
                },
                "recent_transactions": [
                    {
                        "id": str(t.id),
                        "type": t.type,
                        "amount": float(t.amount),
                        "category": getattr(t.category, "name", None),
                        "date": t.date,
                    }
                    for t in Transaction.objects.filter(owner=user).order_by("-date")[:5]
                ],
                "next_installments": [
                    {
                        "debt": inst.debt.name,
                        "due_date": inst.due_date,
                        "amount_due": float(inst.amount_due),
                    }
                    for inst in next_installments
                ],
                "goals": [
                    {
                        "name": g.name,
                        "progress": float(getattr(g, "progress", 0) or 0),
                        "target": float(g.target_amount),
                    }
                    for g in goals
                ],
                "teams": [{"team": m.team.name, "role": m.role} for m in teams],
                "alerts": [
                    {
                        "title": a.title,
                        "message": a.message,
                        "type": a.type,
                        "severity": a.severity,
                    }
                    for a in latest_alerts
                ],
                "plan_limits": user.get_plan_config(),
            }
        )
