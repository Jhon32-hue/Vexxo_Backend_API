from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from rest_framework import permissions, views
from rest_framework.response import Response

from api.mobile.market_data import build_mobile_market_snapshot
from alerts.alerts.models.outbox import AlertDomainEventOutbox
from alerts.alerts.models.alerts import Alert, AlertSeverity, AlertStatus
from finance.accounts.models import Account, AccountOwnerMetrics, AccountPortfolioSnapshot, AccountRiskSnapshot, DomainEventOutbox
from finance.accounts.models.account import AccountStatus
from finance.accounts.services.intelligence_dispatch_service import get_account_intelligence_projection_status
from finance.accounts.services.permission_service import account_scope_for_user
from finance.budgets.Models.shared_budget import SharedBudget
from finance.budgets.services import build_budget_monthly_overview, list_shared_budgets_with_metrics
from finance.categories.models import Category
from finance.fx.models import Currency, ExchangeRate
from finance.transactions.Models.outbox import TransactionDomainEventOutbox
from finance.transactions.Models.transacciones import Transaction
from identity.eventing.models import IdentityDomainEventOutbox, UserProductUsageProjection
from identity.users.services.product_access_service import (
    capabilities_for_user,
    effective_plan_for_user,
    get_user_usage_snapshot,
)
from notifications.deliveries.models import NotificationDelivery, NotificationStatus
from payments.payment_intents.models import PaymentDomainEventOutbox
from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate
from planning.goals.models import Goal
from social.teams.models import Membership, Team


def _visible_shared_budgets(user):
    return SharedBudget.objects.filter(
        Q(team__owner=user)
        | Q(team__memberships__user=user, team__memberships__is_active=True)
    ).distinct()


class MobileBootstrapView(views.APIView):
    """
    BFF mobile para arranque/sync incremental.

    Compone snapshots de lectura de varios bounded contexts. No reemplaza las
    APIs de escritura ni permite que mobile salte validaciones de dominio.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        client_versions = self._client_section_versions(request)
        section_states = self._section_states(user)
        section_builders = self._section_builders(user)
        sections = {
            key: self._build_section_if_changed(
                key=key,
                state=state,
                client_versions=client_versions,
                builder=section_builders[key],
            )
            for key, state in section_states.items()
        }

        return Response(
            {
                "ok": True,
                "server_time": now.isoformat(),
                "schema_version": "mobile.bootstrap.v1",
                "sections": sections,
                "sync_policy": {
                    "read_cache_ttl_seconds": 300,
                    "background_sync_min_interval_minutes": 15,
                    "retry_backoff": "exponential",
                },
                "meta": {
                    "section_versions": {key: value["version"] for key, value in sections.items()},
                    "section_catalog": self._section_catalog(),
                },
            }
        )

    def _client_section_versions(self, request) -> dict:
        raw = request.headers.get("X-Vexxo-Mobile-Section-Versions") or request.query_params.get("section_versions") or "{}"
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(decoded, dict):
            return {}
        return {str(key): str(value) for key, value in decoded.items()}

    def _section_builders(self, user) -> dict:
        return {
            "dashboard": lambda: self._dashboard_section(user),
            "accounts": lambda: self._accounts_section(user),
            "categories": lambda: self._categories_section(user),
            "shared_budgets": lambda: self._shared_budgets_section(user),
            "budget_overview": lambda: self._budget_overview_section(user),
            "scheduled_payments": lambda: self._scheduled_payments_section(user),
            "goals": lambda: self._goals_section(user),
            "fx_rates": lambda: self._fx_rates_section(user),
            "notifications": lambda: self._notifications_section(user),
            "alerts": lambda: self._alerts_section(user),
            "teams": lambda: self._teams_section(user),
            "capabilities": lambda: self._capabilities_section(user),
        }

    def _build_section_if_changed(self, *, key: str, state: dict, client_versions: dict, builder) -> dict:
        if client_versions.get(key) == state["version"]:
            return {
                "version": state["version"],
                "server_updated_at": state["server_updated_at"],
                "unchanged": True,
                "data": None,
            }

        section = builder()
        return {
            **section,
            # sync-state y bootstrap deben publicar exactamente la misma version.
            "version": state["version"],
            "server_updated_at": state["server_updated_at"],
            "unchanged": False,
        }

    def _section_states(self, user) -> dict:
        account_scope = account_scope_for_user(user, Account.objects.all()).exclude(status=AccountStatus.CLOSED)
        account_stats = account_scope.aggregate(updated_at=Max("updated_at"), count=Count("id"))
        category_stats = Category.objects.filter(owner=user).aggregate(updated_at=Max("updated_at"), count=Count("id"))
        shared_stats = _visible_shared_budgets(user).aggregate(
            updated_at=Max("updated_at"),
            count=Count("id", distinct=True),
        )
        transaction_updated_at = Transaction.objects.filter(owner=user).aggregate(value=Max("updated_at"))["value"]
        payment_template_stats = PaymentTemplate.objects.filter(owner=user).aggregate(updated_at=Max("updated_at"), count=Count("id"))
        payment_run_updated_at = PaymentScheduleRun.objects.filter(owner=user).aggregate(value=Max("updated_at"))["value"]
        goal_stats = Goal.objects.filter(owner=user).aggregate(
            updated_at=Max("updated_at"),
            count=Count("id"),
        )
        fx_updated_at = ExchangeRate.objects.filter(is_active=True).aggregate(value=Max("observed_at"))["value"]
        notification_stats = NotificationDelivery.objects.filter(owner=user).aggregate(updated_at=Max("updated_at"), count=Count("id"))
        alert_stats = Alert.objects.filter(owner=user).aggregate(updated_at=Max("updated_at"), count=Count("id"))
        team_stats = Team.objects.filter(Q(owner=user) | Q(memberships__user=user, memberships__is_active=True)).distinct().aggregate(
            updated_at=Max("updated_at"),
            count=Count("id", distinct=True),
        )
        membership_stats = Membership.objects.filter(user=user, is_active=True).aggregate(updated_at=Max("updated_at"))
        usage_projection = UserProductUsageProjection.objects.filter(owner=user).first()

        dashboard_updated_at = max(
            filter(
                None,
                [
                    getattr(AccountOwnerMetrics.objects.filter(owner=user).first(), "generated_at", None),
                    getattr(AccountPortfolioSnapshot.objects.filter(owner=user).first(), "generated_at", None),
                    getattr(AccountRiskSnapshot.objects.filter(owner=user).first(), "generated_at", None),
                    transaction_updated_at,
                    getattr(user, "updated_at", None),
                ],
            ),
            default=timezone.now(),
        )
        capabilities_updated_at = max(
            filter(
                None,
                [
                    getattr(user, "updated_at", None),
                    getattr(usage_projection, "refreshed_at", None),
                ],
            ),
            default=timezone.now(),
        )

        return {
            "dashboard": self._section_state(
                version_key="dashboard",
                updated_at=dashboard_updated_at,
                source="read_model+snapshot",
                owner="identity.users+finance.accounts+finance.transactions",
                extra={"shape": "mobile_dashboard_v1"},
            ),
            "accounts": self._section_state(
                version_key="accounts",
                updated_at=account_stats["updated_at"] or getattr(user, "updated_at", None),
                source="operational_cache",
                owner="finance.accounts",
                extra={"count": int(account_stats["count"] or 0), "shape": "mobile_accounts_v1"},
            ),
            "categories": self._section_state(
                version_key="categories",
                updated_at=category_stats["updated_at"] or getattr(user, "updated_at", None),
                source="reference_data",
                owner="finance.categories",
                extra={"count": int(category_stats["count"] or 0), "shape": "mobile_categories_v1"},
            ),
            "shared_budgets": self._section_state(
                version_key="shared_budgets",
                updated_at=shared_stats["updated_at"] or getattr(user, "updated_at", None),
                source="read_model",
                owner="finance.budgets",
                extra={"count": int(shared_stats["count"] or 0), "shape": "mobile_shared_budgets_v1"},
            ),
            "budget_overview": self._section_state(
                version_key="budget_overview",
                updated_at=max(filter(None, [transaction_updated_at, shared_stats["updated_at"], getattr(user, "updated_at", None)]), default=timezone.now()),
                source="materialized_read_model",
                owner="finance.budgets+finance.transactions+payments.scheduled_payments",
                extra={"shape": "mobile_budget_overview_v1"},
            ),
            "scheduled_payments": self._section_state(
                version_key="scheduled_payments",
                updated_at=max(filter(None, [payment_template_stats["updated_at"], payment_run_updated_at, getattr(user, "updated_at", None)]), default=timezone.now()),
                source="operational_read_model",
                owner="payments.scheduled_payments",
                extra={"count": int(payment_template_stats["count"] or 0), "shape": "mobile_scheduled_payments_v1"},
            ),
            "goals": self._section_state(
                version_key="goals",
                updated_at=goal_stats["updated_at"] or getattr(user, "updated_at", None),
                source="domain_read",
                owner="planning.goals",
                extra={"count": int(goal_stats["count"] or 0), "shape": "mobile_goals_v1"},
            ),
            "fx_rates": self._section_state(
                version_key="fx_rates",
                updated_at=fx_updated_at or getattr(user, "updated_at", None),
                source="reference_data",
                owner="finance.fx",
                extra={"shape": "mobile_fx_rates_v1"},
            ),
            "notifications": self._section_state(
                version_key="notifications",
                updated_at=notification_stats["updated_at"] or getattr(user, "updated_at", None),
                source="durable_inbox",
                owner="notifications.deliveries",
                extra={"count": int(notification_stats["count"] or 0), "shape": "mobile_notifications_v1"},
            ),
            "alerts": self._section_state(
                version_key="alerts",
                updated_at=alert_stats["updated_at"] or getattr(user, "updated_at", None),
                source="durable_business_signal",
                owner="alerts.alerts",
                extra={"count": int(alert_stats["count"] or 0), "shape": "mobile_alerts_v1"},
            ),
            "teams": self._section_state(
                version_key="teams",
                updated_at=max(
                    filter(
                        None,
                        [
                            team_stats["updated_at"],
                            membership_stats["updated_at"],
                            getattr(user, "updated_at", None),
                        ],
                    ),
                    default=timezone.now(),
                ),
                source="domain_read",
                owner="social.teams",
                extra={"count": int(team_stats["count"] or 0), "shape": "mobile_teams_v1"},
            ),
            "capabilities": self._section_state(
                version_key="capabilities",
                updated_at=capabilities_updated_at,
                source="projection",
                owner="identity.users+identity.eventing",
                extra={"shape": "mobile_capabilities_v1"},
            ),
        }

    def _section_state(self, *, version_key: str, updated_at, source: str, owner: str, extra: dict | None = None) -> dict:
        server_updated_at = (updated_at or timezone.now()).isoformat()
        signature = extra or {}
        return {
            "version": self._version_hash(version_key, server_updated_at, signature),
            "server_updated_at": server_updated_at,
            "source": source,
            "owner": owner,
            "signature": signature,
        }

    def _dashboard_section(self, user) -> dict:
        owner_metrics = AccountOwnerMetrics.objects.filter(owner=user).first()
        portfolio = AccountPortfolioSnapshot.objects.filter(owner=user).first()
        risk = AccountRiskSnapshot.objects.filter(owner=user).first()
        accounts_qs = Account.objects.filter(owner=user).exclude(status=AccountStatus.CLOSED)
        month_start = timezone.localdate().replace(day=1)

        total_balance = (
            getattr(owner_metrics, "total_cached_balance_in_base", None)
            if owner_metrics is not None
            else accounts_qs.aggregate(total=Sum("balance"))["total"] or Decimal("0")
        )
        expenses_month = (
            Transaction.objects.filter(owner=user, type="expense", date__gte=month_start).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        income_month = (
            Transaction.objects.filter(owner=user, type="income", date__gte=month_start).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        updated_at = max(
            filter(
                None,
                [
                    getattr(owner_metrics, "generated_at", None),
                    getattr(portfolio, "generated_at", None),
                    getattr(risk, "generated_at", None),
                    Transaction.objects.filter(owner=user).aggregate(value=Max("updated_at"))["value"],
                    getattr(user, "updated_at", None),
                ],
            ),
            default=timezone.now(),
        )
        data = {
            "user": {
                "id": str(user.pk),
                "full_name": user.display_name,
                "preferred_currency": user.preferred_currency,
                "plan": user.plan,
                "effective_plan": effective_plan_for_user(user),
                "status": user.status,
                "onboarding_completed": bool(user.onboarding_completed),
            },
            "summary": {
                "total_balance": float(total_balance or 0),
                "monthly_expenses": float(expenses_month),
                "monthly_income": float(income_month),
            },
            "accounts": {
                "owner_metrics": {
                    "total_accounts": getattr(owner_metrics, "total_accounts", 0),
                    "active_accounts": getattr(owner_metrics, "active_accounts", 0),
                    "shared_accounts": getattr(owner_metrics, "shared_accounts", 0),
                    "external_accounts": getattr(owner_metrics, "external_accounts", 0),
                    "currencies_count": getattr(owner_metrics, "currencies_count", 0),
                }
                if owner_metrics
                else None,
                "projection_status": get_account_intelligence_projection_status(owner=user),
            },
        }
        return self._section(data=data, updated_at=updated_at, version_key="dashboard")

    def _accounts_section(self, user) -> dict:
        qs = (
            account_scope_for_user(user, Account.objects.all())
            .exclude(status=AccountStatus.CLOSED)
            .order_by("display_order", "name", "id")
        )
        updated_at = qs.aggregate(value=Max("updated_at"))["value"] or getattr(user, "updated_at", None) or timezone.now()
        data = [
            {
                "id": account.pk,
                "name": account.name,
                "type": account.type,
                "role": account.role,
                "status": account.status,
                "currency": account.currency,
                "balance": str(account.balance),
                "is_primary": bool(account.is_primary),
                "sync_status": account.sync_status,
                "owner_id": account.owner_id,
            }
            for account in qs[:50]
        ]
        return self._section(data=data, updated_at=updated_at, version_key="accounts")

    def _categories_section(self, user) -> dict:
        qs = Category.objects.filter(owner=user).order_by("type", "name")
        updated_at = qs.aggregate(value=Max("updated_at"))["value"] or getattr(user, "updated_at", None) or timezone.now()
        data = [
            {
                "id": category.pk,
                "name": category.name,
                "type": category.type,
                "updated_at": category.updated_at.isoformat() if category.updated_at else "",
            }
            for category in qs
        ]
        return self._section(data=data, updated_at=updated_at, version_key="categories")

    def _shared_budgets_section(self, user) -> dict:
        rows = list_shared_budgets_with_metrics(user=user, month=None, team_id=None)
        updated_at = (
            _visible_shared_budgets(user).aggregate(value=Max("updated_at"))["value"]
            or getattr(user, "updated_at", None)
            or timezone.now()
        )
        return self._section(data=rows, updated_at=updated_at, version_key="shared_budgets")

    def _budget_overview_section(self, user) -> dict:
        month = timezone.localdate().strftime("%Y-%m")
        data = build_budget_monthly_overview(owner=user, month=month)
        updated_at = max(
            filter(
                None,
                [
                    Transaction.objects.filter(owner=user).aggregate(value=Max("updated_at"))["value"],
                    _visible_shared_budgets(user).aggregate(value=Max("updated_at"))["value"],
                    PaymentTemplate.objects.filter(owner=user).aggregate(value=Max("updated_at"))["value"],
                    getattr(user, "updated_at", None),
                ],
            ),
            default=timezone.now(),
        )
        return self._section(data=data, updated_at=updated_at, version_key="budget_overview")

    def _scheduled_payments_section(self, user) -> dict:
        template_qs = (
            PaymentTemplate.objects.filter(owner=user, is_active=True)
            .select_related("account", "category", "shared_budget")
            .order_by("next_run_at", "name", "id")
        )
        run_qs = (
            PaymentScheduleRun.objects.filter(
                owner=user,
                status__in=[
                    PaymentScheduleRun.Status.SCHEDULED,
                    PaymentScheduleRun.Status.DUE,
                    PaymentScheduleRun.Status.OVERDUE,
                    PaymentScheduleRun.Status.POSTPONED,
                    PaymentScheduleRun.Status.FAILED,
                ],
            )
            .select_related("template")
            .order_by("due_on", "scheduled_for", "id")
        )
        templates = [self._scheduled_template_payload(template) for template in template_qs[:30]]
        runs = [self._scheduled_run_payload(run) for run in run_qs[:40]]
        template_stats = template_qs.aggregate(
            updated_at=Max("updated_at"),
            active=Count("id"),
        )
        run_stats = run_qs.aggregate(
            updated_at=Max("updated_at"),
            open=Count("id"),
            overdue=Count("id", filter=Q(status=PaymentScheduleRun.Status.OVERDUE)),
            due=Count("id", filter=Q(status=PaymentScheduleRun.Status.DUE)),
        )
        updated_at = max(
            filter(
                None,
                [
                    template_stats["updated_at"],
                    run_stats["updated_at"],
                    getattr(user, "updated_at", None),
                ],
            ),
            default=timezone.now(),
        )
        data = {
            "templates": templates,
            "runs": runs,
            "summary": {
                "active_templates": int(template_stats["active"] or 0),
                "open_runs": int(run_stats["open"] or 0),
                "overdue_runs": int(run_stats["overdue"] or 0),
                "due_runs": int(run_stats["due"] or 0),
            },
        }
        return self._section(data=data, updated_at=updated_at, version_key="scheduled_payments")

    def _scheduled_template_payload(self, template: PaymentTemplate) -> dict:
        return {
            "id": template.pk,
            "name": template.name,
            "payment_type": template.payment_type,
            "amount_mode": template.amount_mode,
            "amount": str(template.default_amount or ""),
            "currency": template.currency,
            "cadence": template.cadence,
            "next_run_at": template.next_run_at.isoformat() if template.next_run_at else "",
            "account_id": template.account_id,
            "account_name": getattr(template.account, "name", ""),
            "category_id": template.category_id,
            "category_name": getattr(template.category, "name", ""),
            "shared_budget_id": template.shared_budget_id,
            "shared_budget_name": getattr(template.shared_budget, "name", ""),
            "beneficiary_name": template.beneficiary_name,
        }

    def _scheduled_run_payload(self, run: PaymentScheduleRun) -> dict:
        return {
            "id": run.pk,
            "template_id": run.template_id,
            "template_name": getattr(run.template, "name", ""),
            "status": run.status,
            "scheduled_for": run.scheduled_for.isoformat() if run.scheduled_for else "",
            "due_on": run.due_on.isoformat() if run.due_on else "",
            "amount": str(run.expected_amount or ""),
            "currency": run.expected_currency,
            "reminder_stage": run.reminder_stage,
            "failure_message": run.failure_message,
        }

    def _goals_section(self, user) -> dict:
        qs = Goal.objects.filter(owner=user).select_related("account").order_by("-active", "target_date", "name", "id")
        data = [
            {
                "id": goal.pk,
                "name": goal.name,
                "target_amount": str(goal.target_amount),
                "target_date": goal.target_date.isoformat() if goal.target_date else "",
                "progress": str(goal.progress),
                "completion_percentage": str(goal.completion_percentage),
                "account_id": goal.account_id,
                "account_name": getattr(goal.account, "name", ""),
                "currency": getattr(goal.account, "currency", getattr(user, "preferred_currency", "COP")),
                "active": bool(goal.active),
                "status": goal.status,
                "completed_at": goal.completed_at.isoformat() if goal.completed_at else "",
                "strategy": goal.strategy or {},
            }
            for goal in qs[:30]
        ]
        return self._section(data=data, updated_at=getattr(user, "updated_at", None) or timezone.now(), version_key="goals")

    def _fx_rates_section(self, user) -> dict:
        preferred_currency = getattr(user, "preferred_currency", "COP") or "COP"
        currencies = [{"code": code, "name": label} for code, label in Currency.choices]
        rates = []
        seen_pairs = set()
        qs = ExchangeRate.objects.filter(is_active=True).order_by("base_currency", "quote_currency", "-observed_at")
        for rate in qs[:250]:
            pair = (rate.base_currency, rate.quote_currency)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            rates.append(
                {
                    "base_currency": rate.base_currency,
                    "quote_currency": rate.quote_currency,
                    "rate": str(rate.rate),
                    "provider": rate.provider,
                    "observed_at": rate.observed_at.isoformat() if rate.observed_at else "",
                }
            )
            if len(rates) >= 60:
                break
        updated_at = ExchangeRate.objects.filter(is_active=True).aggregate(value=Max("observed_at"))["value"] or timezone.now()
        return self._section(
            data={
                "preferred_currency": preferred_currency,
                "currencies": currencies,
                "rates": rates,
            },
            updated_at=updated_at,
            version_key="fx_rates",
        )

    def _capabilities_section(self, user) -> dict:
        usage_projection = UserProductUsageProjection.objects.filter(owner=user).first()
        data = {
            "plan": effective_plan_for_user(user),
            "capabilities": capabilities_for_user(user),
            "usage": get_user_usage_snapshot(user),
        }
        updated_at = max(
            filter(None, [getattr(user, "updated_at", None), getattr(usage_projection, "refreshed_at", None)]),
            default=timezone.now(),
        )
        return self._section(data=data, updated_at=updated_at, version_key="capabilities")

    def _notifications_section(self, user) -> dict:
        notification_qs = NotificationDelivery.objects.filter(owner=user).order_by("-created_at")
        items = [
            {
                "id": notification.id,
                "channel": notification.channel,
                "status": notification.status,
                "event_type": notification.event_type,
                "source": notification.source,
                "title": notification.title,
                "message": notification.message,
                "payload": dict(notification.payload or {}),
                "is_read": notification.is_read,
                "created_at": notification.created_at.isoformat() if notification.created_at else None,
                "delivered_at": notification.delivered_at.isoformat() if notification.delivered_at else None,
                "read_at": notification.read_at.isoformat() if notification.read_at else None,
            }
            for notification in notification_qs[:12]
        ]
        stats = notification_qs.aggregate(
            updated_at=Max("updated_at"),
            total=Count("id"),
            unread=Count("id", filter=~Q(status=NotificationStatus.READ)),
            read=Count("id", filter=Q(status=NotificationStatus.READ)),
        )
        updated_at = stats["updated_at"] or getattr(user, "updated_at", None) or timezone.now()
        data = {
            "stats": {
                "total": int(stats["total"] or 0),
                "unread": int(stats["unread"] or 0),
                "read": int(stats["read"] or 0),
            },
            "items": items,
        }
        return self._section(data=data, updated_at=updated_at, version_key="notifications")

    def _alerts_section(self, user) -> dict:
        alert_qs = Alert.objects.filter(owner=user).order_by("-created_at")
        items = [
            {
                "id": alert.id,
                "type": alert.type,
                "category": alert.category,
                "severity": alert.severity,
                "status": alert.status,
                "title": alert.title,
                "message": alert.message,
                "ai_summary": alert.ai_summary,
                "ai_tags": list(alert.ai_tags or []),
                "payload": dict(alert.payload or {}),
                "is_active": alert.is_active,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "read_at": alert.read_at.isoformat() if alert.read_at else None,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            }
            for alert in alert_qs[:10]
        ]
        stats = alert_qs.aggregate(
            updated_at=Max("updated_at"),
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            new=Count("id", filter=Q(status=AlertStatus.NEW)),
            critical=Count("id", filter=Q(is_active=True, severity=AlertSeverity.CRITICAL)),
        )
        updated_at = stats["updated_at"] or getattr(user, "updated_at", None) or timezone.now()
        data = {
            "stats": {
                "total": int(stats["total"] or 0),
                "active": int(stats["active"] or 0),
                "new": int(stats["new"] or 0),
                "critical": int(stats["critical"] or 0),
            },
            "items": items,
        }
        return self._section(data=data, updated_at=updated_at, version_key="alerts")

    def _teams_section(self, user) -> dict:
        team_qs = (
            Team.objects.filter(Q(owner=user) | Q(memberships__user=user, memberships__is_active=True))
            .distinct()
            .annotate(active_members_count=Count("memberships", filter=Q(memberships__is_active=True), distinct=True))
            .order_by("-created_at")
        )
        memberships = Membership.objects.filter(user=user, is_active=True)
        membership_by_team = {membership.team_id: membership.role for membership in memberships}
        owned_count = Team.objects.filter(owner=user).count()
        member_count = memberships.exclude(role="owner").values("team_id").distinct().count()
        items = [
            {
                "id": team.id,
                "name": team.name,
                "description": team.description,
                "is_personal": team.is_personal,
                "is_owner": team.owner_id == user.pk,
                "role": "owner" if team.owner_id == user.pk else membership_by_team.get(team.id, "viewer"),
                "members_count": int(getattr(team, "active_members_count", 0)),
                "created_at": team.created_at.isoformat() if team.created_at else None,
            }
            for team in team_qs[:8]
        ]
        updated_at = max(
            filter(
                None,
                [
                    team_qs.aggregate(value=Max("updated_at"))["value"],
                    memberships.aggregate(value=Max("updated_at"))["value"],
                    getattr(user, "updated_at", None),
                ],
            ),
            default=timezone.now(),
        )
        data = {
            "stats": {
                "total": team_qs.count(),
                "owned": owned_count,
                "member": member_count,
                "personal": team_qs.filter(is_personal=True).count(),
            },
            "items": items,
        }
        return self._section(data=data, updated_at=updated_at, version_key="teams")

    def _section(self, *, data, updated_at, version_key: str) -> dict:
        server_updated_at = updated_at.isoformat() if updated_at else timezone.now().isoformat()
        version = self._version_hash(version_key, server_updated_at)
        return {
            "version": version,
            "server_updated_at": server_updated_at,
            "data": data,
        }

    def _version_hash(self, version_key: str, server_updated_at: str, extra: dict | None = None) -> str:
        encoded = json.dumps(
            {"key": version_key, "server_updated_at": server_updated_at, "extra": extra or {}},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    def _section_catalog(self) -> dict:
        return {
            "dashboard": {
                "owner": "identity.users+finance.accounts+finance.transactions",
                "source": "read_model+snapshot",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "domain_endpoints",
            },
            "accounts": {
                "owner": "finance.accounts",
                "source": "operational_cache",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "finance.accounts",
            },
            "categories": {
                "owner": "finance.categories",
                "source": "reference_data",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "finance.categories",
            },
            "shared_budgets": {
                "owner": "finance.budgets",
                "source": "read_model",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "finance.budgets",
            },
            "budget_overview": {
                "owner": "finance.budgets+finance.transactions+payments.scheduled_payments",
                "source": "materialized_read_model",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "finance.budgets",
            },
            "scheduled_payments": {
                "owner": "payments.scheduled_payments",
                "source": "operational_read_model",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "payments.scheduled_payments",
            },
            "goals": {
                "owner": "planning.goals",
                "source": "domain_read",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "planning.goals",
            },
            "fx_rates": {
                "owner": "finance.fx",
                "source": "reference_data",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "finance.fx",
            },
            "notifications": {
                "owner": "notifications.deliveries",
                "source": "durable_inbox",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "notifications.deliveries",
            },
            "alerts": {
                "owner": "alerts.alerts",
                "source": "durable_business_signal",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "alerts.alerts",
            },
            "teams": {
                "owner": "social.teams",
                "source": "domain_read",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "social.teams",
            },
            "capabilities": {
                "owner": "identity.users+identity.eventing",
                "source": "projection",
                "truth": "backend",
                "bootstrap_section": True,
                "write_path": "identity.users",
            },
        }

    def _client_pending_writes_count(self, request) -> int:
        raw = request.headers.get("X-Vexxo-Mobile-Pending-Writes") or request.query_params.get("pending_writes") or "0"
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0

    def _server_cursor(self, section_states: dict, outbox_state: dict) -> str:
        timestamps = [
            value.get("server_updated_at")
            for value in section_states.values()
            if value.get("server_updated_at")
        ]
        if outbox_state.get("latest_occurred_at"):
            timestamps.append(outbox_state["latest_occurred_at"])
        return max(timestamps) if timestamps else timezone.now().isoformat()

    def _outbox_state(self, user) -> dict:
        account_ids = list(
            account_scope_for_user(user, Account.objects.all())
            .exclude(status=AccountStatus.CLOSED)
            .values_list("pk", flat=True)[:250]
        )
        transaction_ids = list(Transaction.objects.filter(owner=user).values_list("pk", flat=True)[:250])
        account_qs = DomainEventOutbox.objects.filter(aggregate_type="account", aggregate_id__in=[str(pk) for pk in account_ids])
        transaction_qs = TransactionDomainEventOutbox.objects.filter(
            aggregate_type="transaction",
            aggregate_id__in=[str(pk) for pk in transaction_ids],
        )
        identity_qs = IdentityDomainEventOutbox.objects.filter(aggregate_id=str(user.pk))
        payment_qs = PaymentDomainEventOutbox.objects.filter(aggregate_id=str(user.pk))
        alert_qs = AlertDomainEventOutbox.objects.filter(aggregate_id=str(user.pk))

        contexts = {
            "finance.accounts": account_qs,
            "finance.transactions": transaction_qs,
            "identity": identity_qs,
            "payments": payment_qs,
            "alerts": alert_qs,
        }
        by_context = {}
        latest = None
        for name, qs in contexts.items():
            context_state = qs.aggregate(
                latest=Max("occurred_at"),
                pending=Count("id", filter=Q(status="pending")),
                processing=Count("id", filter=Q(status="processing")),
                failed=Count("id", filter=Q(status="failed")),
                dead_letter=Count("id", filter=Q(status="dead_letter")),
            )
            latest_for_context = context_state["latest"]
            latest = max(filter(None, [latest, latest_for_context]), default=latest)
            by_context[name] = {
                "pending": int(context_state["pending"] or 0),
                "processing": int(context_state["processing"] or 0),
                "failed": int(context_state["failed"] or 0),
                "dead_letter": int(context_state["dead_letter"] or 0),
            }
        return {
            "by_context": by_context,
            "latest_occurred_at": latest.isoformat() if latest else None,
        }


class MobileSyncStateView(MobileBootstrapView):
    """
    Estado liviano para decidir si mobile debe subir pendientes o pedir bootstrap.

    No transporta datos de pantalla; compara versiones y reporta direccion de sync.
    """

    def get(self, request):
        user = request.user
        client_versions = self._client_section_versions(request)
        pending_client_writes = self._client_pending_writes_count(request)
        section_states = self._section_states(user)
        outbox_state = self._outbox_state(user)

        sections = {}
        changed_sections = []
        for key, state in section_states.items():
            changed = client_versions.get(key) != state["version"]
            if changed:
                changed_sections.append(key)
            sections[key] = {
                **state,
                "changed": changed,
                "client_version": client_versions.get(key, ""),
                **self._section_catalog()[key],
            }

        next_cursor = self._server_cursor(section_states, outbox_state)
        should_upload_first = pending_client_writes > 0
        should_fetch_bootstrap = bool(changed_sections) and not should_upload_first

        return Response(
            {
                "ok": True,
                "schema_version": "mobile.sync_state.v1",
                "server_time": timezone.now().isoformat(),
                "sync": {
                    "direction": "upload_then_pull" if should_upload_first else "pull_or_idle",
                    "pending_client_writes": pending_client_writes,
                    "changed_sections": changed_sections,
                    "should_upload_first": should_upload_first,
                    "should_fetch_bootstrap": should_fetch_bootstrap,
                    "next_cursor": next_cursor,
                    "recommended_next_sync_seconds": 900 if not changed_sections and not should_upload_first else 60,
                },
                "sections": sections,
                "backend_runtime": {
                    "database_truth": "postgresql_oltp",
                    "event_transport": "bounded_context_outbox",
                    "read_strategy": "operational_cache+snapshots+materialized_read_models",
                    "outbox_state": outbox_state,
                },
                "mobile_contract": {
                    "client_writes": "mobile pushes confirmed offline mutations to domain APIs first",
                    "server_reads": "mobile pulls sync-state/bootstrap after writes are accepted",
                    "authority": "backend validates permissions, ledger and final state",
                },
            }
        )


class MobileMarketsView(views.APIView):
    """
    BFF liviano para FX/mercados en mobile.

    Mantiene proveedores externos fuera de Flutter y permite cache, fallback y
    gobierno de datos desde backend.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        base_currency = (
            request.query_params.get("base")
            or getattr(request.user, "preferred_currency", None)
            or "COP"
        )
        return Response(
            {
                "ok": True,
                "schema_version": "mobile.markets.v1",
                "data": build_mobile_market_snapshot(base_currency=base_currency),
            }
        )
