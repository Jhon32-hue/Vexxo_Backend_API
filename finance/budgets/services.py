from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import logging
import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, Sum
from rest_framework.exceptions import PermissionDenied, ValidationError

from alerts.alerts.models import Alert, AlertCategory, AlertSeverity, AlertType
from alerts.alerts.services import create_alert
from common.domain_events import EventPriority
from finance.budgets.attribution import BudgetAttributionSource, BudgetScope
from finance.budgets.domain_events import BudgetDomainEventTypes
from finance.budgets.event_service import publish_budget_event_after_commit
from finance.budgets.models import (
    Budget,
    SharedBudget,
    SharedBudgetTemplateLink,
    SharedBudgetTransactionLink,
)
from finance.categories.models import Category
from finance.transactions.Models import Transaction
from finance.transactions.transaction_state_service import LEDGER_COUNTABLE_STATUSES, is_transaction_countable_for_ledger
from payments.scheduled_payments.models import PaymentTemplate
from social.teams.models import Membership, Team

logger = logging.getLogger(__name__)

User = get_user_model()

MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
ZERO = Decimal("0.00")
DEFAULT_ALERT_THRESHOLDS = [30, 50, 70, 100]
BUDGET_ALERT_SOURCE = "finance.budgets.monitoring"
TEAM_MANAGE_ROLES = {"owner", "accountant"}


@dataclass(frozen=True)
class BudgetPeriod:
    month: str
    start: date
    end_exclusive: date


@dataclass(frozen=True)
class BudgetMetrics:
    actual_spent: Decimal
    committed_spent: Decimal
    projected_spent: Decimal
    remaining: Decimal
    available_after_committed: Decimal
    actual_percentage_used: Decimal
    projected_percentage_used: Decimal
    is_exceeded: bool
    is_projected_exceeded: bool
    alert_state: str
    triggered_thresholds: list[int]
    highest_triggered_threshold: int | None


def _quantize(value) -> Decimal:
    return Decimal(value or ZERO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_budget_month(raw_month: str | date) -> str:
    if isinstance(raw_month, date):
        return raw_month.strftime("%Y-%m")
    value = str(raw_month or "").strip()
    if not MONTH_PATTERN.match(value):
        raise ValidationError({"month": "El periodo debe usar formato YYYY-MM."})
    year, month = value.split("-")
    month_number = int(month)
    if month_number < 1 or month_number > 12:
        raise ValidationError({"month": "El periodo debe tener un mes valido entre 01 y 12."})
    return f"{int(year):04d}-{month_number:02d}"


def resolve_budget_period(raw_month: str | date) -> BudgetPeriod:
    month = normalize_budget_month(raw_month)
    year, month_number = (int(part) for part in month.split("-"))
    start = date(year, month_number, 1)
    if month_number == 12:
        end_exclusive = date(year + 1, 1, 1)
    else:
        end_exclusive = date(year, month_number + 1, 1)
    return BudgetPeriod(month=month, start=start, end_exclusive=end_exclusive)


def normalize_alert_thresholds(raw_thresholds) -> list[int]:
    if not raw_thresholds:
        thresholds = list(DEFAULT_ALERT_THRESHOLDS)
    else:
        try:
            thresholds = sorted({int(value) for value in raw_thresholds})
        except Exception as exc:  # pragma: no cover - defensive branch
            raise ValidationError({"alert_thresholds": "Los umbrales deben ser numeros enteros entre 1 y 100."}) from exc
    if any(value < 1 or value > 100 for value in thresholds):
        raise ValidationError({"alert_thresholds": "Cada umbral debe estar entre 1 y 100."})
    if 100 not in thresholds:
        thresholds.append(100)
    return sorted(set(thresholds))


def _validate_amount(raw_amount) -> Decimal:
    try:
        amount = _quantize(Decimal(raw_amount))
    except Exception as exc:  # pragma: no cover - defensive branch
        raise ValidationError({"amount": "El monto del presupuesto no es valido."}) from exc
    if amount <= ZERO:
        raise ValidationError({"amount": "El monto del presupuesto debe ser mayor que cero."})
    return amount


def _load_expense_category_for_owner(owner, category_id) -> Category:
    category = Category.objects.filter(owner=owner, pk=category_id, type="expense").first()
    if not category:
        raise ValidationError({"category": "La categoria no existe, no pertenece al usuario o no es de gasto."})
    return category


def _budget_expense_queryset(owner, month: str):
    period = resolve_budget_period(month)
    return Transaction.objects.filter(
        owner=owner,
        type=Transaction.Type.EXPENSE,
        status__in=LEDGER_COUNTABLE_STATUSES,
        confirmed=True,
        affects_balance=True,
        date__gte=period.start,
        date__lt=period.end_exclusive,
    )


def _compute_budget_metrics(*, amount: Decimal, actual_spent: Decimal, committed_spent: Decimal, thresholds: list[int]) -> BudgetMetrics:
    amount = _quantize(amount)
    actual_spent = _quantize(actual_spent)
    committed_spent = _quantize(committed_spent)
    projected_spent = _quantize(actual_spent + committed_spent)
    remaining = _quantize(amount - actual_spent)
    available_after_committed = _quantize(amount - projected_spent)
    if amount <= ZERO:
        actual_percentage = Decimal("0.00")
        projected_percentage = Decimal("0.00")
    else:
        actual_percentage = _quantize((actual_spent / amount) * Decimal("100"))
        projected_percentage = _quantize((projected_spent / amount) * Decimal("100"))
    triggered_thresholds = [threshold for threshold in thresholds if actual_percentage >= Decimal(threshold)]
    highest_triggered_threshold = max(triggered_thresholds) if triggered_thresholds else None
    is_exceeded = actual_spent > amount
    is_projected_exceeded = projected_spent > amount
    if is_exceeded:
        alert_state = "exceeded"
    elif highest_triggered_threshold is not None:
        alert_state = f"threshold_{highest_triggered_threshold}"
    else:
        alert_state = "ok"
    return BudgetMetrics(
        actual_spent=actual_spent,
        committed_spent=committed_spent,
        projected_spent=projected_spent,
        remaining=remaining,
        available_after_committed=available_after_committed,
        actual_percentage_used=actual_percentage,
        projected_percentage_used=projected_percentage,
        is_exceeded=is_exceeded,
        is_projected_exceeded=is_projected_exceeded,
        alert_state=alert_state,
        triggered_thresholds=triggered_thresholds,
        highest_triggered_threshold=highest_triggered_threshold,
    )


def _serialize_metrics(metrics: BudgetMetrics) -> dict:
    return {
        "actual_spent": str(metrics.actual_spent),
        "committed_spent": str(metrics.committed_spent),
        "projected_spent": str(metrics.projected_spent),
        "remaining": str(metrics.remaining),
        "available_after_committed": str(metrics.available_after_committed),
        "actual_percentage_used": str(metrics.actual_percentage_used),
        "projected_percentage_used": str(metrics.projected_percentage_used),
        "is_exceeded": metrics.is_exceeded,
        "is_projected_exceeded": metrics.is_projected_exceeded,
        "alert_state": metrics.alert_state,
        "triggered_thresholds": metrics.triggered_thresholds,
        "highest_triggered_threshold": metrics.highest_triggered_threshold,
    }


def _serialize_thresholds(thresholds: list[int]) -> list[int]:
    return list(normalize_alert_thresholds(thresholds))


def _serialize_category_budget_row(budget: Budget, metrics: BudgetMetrics) -> dict:
    thresholds = normalize_alert_thresholds(budget.alert_thresholds)
    return {
        "id": budget.pk,
        "scope_type": "personal_category",
        "owner_id": budget.owner_id,
        "month": budget.month,
        "amount": str(_quantize(budget.amount)),
        "alert_thresholds": thresholds,
        "category": {
            "id": budget.category_id,
            "name": budget.category.name,
            "type": budget.category.type,
        },
        "metrics": _serialize_metrics(metrics),
    }


def _serialize_shared_budget_row(budget: SharedBudget, metrics: BudgetMetrics) -> dict:
    thresholds = normalize_alert_thresholds(budget.alert_thresholds)
    linked_transactions_count = getattr(budget, "_linked_transactions_count", None)
    if linked_transactions_count is None:
        linked_transactions_count = budget.transaction_links.count()
    linked_templates_count = getattr(budget, "_linked_templates_count", None)
    if linked_templates_count is None:
        linked_templates_count = budget.template_links.count()
    return {
        "id": budget.pk,
        "scope_type": "shared",
        "owner_id": budget.owner_id,
        "month": budget.month,
        "name": budget.name,
        "amount": str(_quantize(budget.amount)),
        "alert_thresholds": thresholds,
        "notes": budget.notes,
        "team": {
            "id": budget.team_id,
            "name": budget.team.name,
            "owner_id": budget.team.owner_id,
        },
        "linked_transactions_count": linked_transactions_count,
        "linked_templates_count": linked_templates_count,
        "metrics": _serialize_metrics(metrics),
    }


def _summarize_rows(rows: list[dict], *, scope_type: str, month: str | None = None) -> dict:
    total_planned = ZERO
    total_actual = ZERO
    total_committed = ZERO
    total_projected = ZERO
    exceeded_count = 0
    projected_exceeded_count = 0
    triggered_budget_count = 0
    for row in rows:
        total_planned += Decimal(row["amount"])
        metrics = row["metrics"]
        total_actual += Decimal(metrics["actual_spent"])
        total_committed += Decimal(metrics["committed_spent"])
        total_projected += Decimal(metrics["projected_spent"])
        if metrics["is_exceeded"]:
            exceeded_count += 1
        if metrics["is_projected_exceeded"]:
            projected_exceeded_count += 1
        if metrics["alert_state"] != "ok":
            triggered_budget_count += 1
    return {
        "scope_type": scope_type,
        "month": month or "",
        "count": len(rows),
        "total_planned": str(_quantize(total_planned)),
        "total_actual": str(_quantize(total_actual)),
        "total_committed": str(_quantize(total_committed)),
        "total_projected": str(_quantize(total_projected)),
        "exceeded_count": exceeded_count,
        "projected_exceeded_count": projected_exceeded_count,
        "triggered_budget_count": triggered_budget_count,
    }


def _team_membership_for_user(team: Team, user) -> Membership | None:
    if not user or not user.is_authenticated:
        return None
    return Membership.objects.filter(team=team, user=user, is_active=True).first()


def _assert_can_view_team_budget(user, team: Team) -> None:
    if team.owner_id == user.id:
        return
    if not _team_membership_for_user(team, user):
        raise PermissionDenied("No puedes ver este presupuesto compartido.")


def _assert_can_manage_team_budget(user, team: Team) -> None:
    if team.owner_id == user.id:
        return
    membership = _team_membership_for_user(team, user)
    if not membership or membership.role not in TEAM_MANAGE_ROLES:
        raise PermissionDenied("No puedes administrar este presupuesto compartido.")


def _load_manageable_team(user, team_id) -> Team:
    team = Team.objects.filter(pk=team_id).first()
    if not team:
        raise ValidationError({"team": "El equipo no existe."})
    _assert_can_manage_team_budget(user, team)
    return team


def _load_visible_shared_budget(user, budget_id: int) -> SharedBudget:
    budget = SharedBudget.objects.filter(pk=budget_id).select_related("team").first()
    if not budget:
        raise PermissionDenied("No puedes ver este presupuesto compartido.")
    _assert_can_view_team_budget(user, budget.team)
    return budget


def _active_member_user_ids_for_team(team: Team) -> set[int]:
    ids = set(
        Membership.objects.filter(team=team, is_active=True).values_list("user_id", flat=True)
    )
    ids.add(team.owner_id)
    return ids


def _validate_transaction_for_shared_budget(shared_budget: SharedBudget, transaction_id: int) -> Transaction:
    tx = Transaction.objects.filter(pk=transaction_id).select_related("account", "category").first()
    if not tx:
        raise ValidationError({"transaction_id": "La transaccion no existe."})
    if tx.type != Transaction.Type.EXPENSE:
        raise ValidationError({"transaction_id": "Solo puedes vincular gastos a un presupuesto compartido."})
    if tx.owner_id not in _active_member_user_ids_for_team(shared_budget.team):
        raise ValidationError({"transaction_id": "La transaccion debe pertenecer a un miembro activo del equipo."})
    return tx


def _validate_payment_template_for_shared_budget(shared_budget: SharedBudget, payment_template_id: int) -> PaymentTemplate:
    template = PaymentTemplate.objects.filter(pk=payment_template_id).select_related("category", "account").first()
    if not template:
        raise ValidationError({"payment_template_id": "La plantilla programada no existe."})
    if template.owner_id not in _active_member_user_ids_for_team(shared_budget.team):
        raise ValidationError({"payment_template_id": "La plantilla debe pertenecer a un miembro activo del equipo."})
    if template.amount_mode != PaymentTemplate.AmountMode.FIXED or template.default_amount is None:
        raise ValidationError({"payment_template_id": "Solo puedes vincular plantillas de monto fijo."})
    return template


def _personal_actual_spent_map(owner, budgets: list[Budget]) -> dict[tuple[str, int], Decimal]:
    months_to_categories: dict[str, set[int]] = defaultdict(set)
    for budget in budgets:
        months_to_categories[budget.month].add(int(budget.category_id))
    mapping: dict[tuple[str, int], Decimal] = {}
    for month, category_ids in months_to_categories.items():
        rows = (
            _budget_expense_queryset(owner, month)
            .filter(Q(budget_scope=BudgetScope.PERSONAL) | Q(budget_scope=""))
            .filter(shared_budget__isnull=True)
            .filter(category_id__in=category_ids)
            .values("category_id")
            .annotate(total=Sum("amount"))
        )
        for row in rows:
            mapping[(month, int(row["category_id"]))] = _quantize(row["total"] or ZERO)
    return mapping


def _template_committed_rows(owner, month: str, category_ids: set[int]):
    period = resolve_budget_period(month)
    rows = (
        PaymentTemplate.objects.filter(
            owner=owner,
            is_active=True,
            amount_mode=PaymentTemplate.AmountMode.FIXED,
            default_amount__isnull=False,
            next_run_at__date__gte=period.start,
            next_run_at__date__lt=period.end_exclusive,
            shared_budget__isnull=True,
            budget_scope__in=[BudgetScope.PERSONAL, ""],
            category_id__in=category_ids,
        )
        .values("category_id")
        .annotate(total=Sum("default_amount"))
    )
    return rows


def _personal_committed_spent_map(owner, budgets: list[Budget]) -> dict[tuple[str, int], Decimal]:
    months_to_categories: dict[str, set[int]] = defaultdict(set)
    for budget in budgets:
        months_to_categories[budget.month].add(int(budget.category_id))
    mapping: dict[tuple[str, int], Decimal] = defaultdict(lambda: ZERO)
    for month, category_ids in months_to_categories.items():
        for row in _template_committed_rows(owner, month, category_ids):
            mapping[(month, int(row["category_id"]))] = _quantize(mapping[(month, int(row["category_id"]))] + (row["total"] or ZERO))
    return dict(mapping)


def list_category_budgets_with_metrics(*, owner, month: str | None = None, category_id: int | None = None) -> dict:
    queryset = Budget.objects.filter(owner=owner).select_related("category").order_by("-month", "category__name")
    normalized_month = normalize_budget_month(month) if month else None
    if normalized_month:
        queryset = queryset.filter(month=normalized_month)
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    budgets = list(queryset)
    actual_map = _personal_actual_spent_map(owner, budgets)
    committed_map = _personal_committed_spent_map(owner, budgets)
    rows = []
    for budget in budgets:
        thresholds = normalize_alert_thresholds(budget.alert_thresholds)
        metrics = _compute_budget_metrics(
            amount=budget.amount,
            actual_spent=actual_map.get((budget.month, int(budget.category_id)), ZERO),
            committed_spent=committed_map.get((budget.month, int(budget.category_id)), ZERO),
            thresholds=thresholds,
        )
        rows.append(_serialize_category_budget_row(budget, metrics))
    return {
        "summary": _summarize_rows(rows, scope_type="personal_category", month=normalized_month),
        "results": rows,
    }


def _shared_actual_spent_map(shared_budgets: list[SharedBudget]) -> dict[int, Decimal]:
    budget_ids = [budget.pk for budget in shared_budgets]
    if not budget_ids:
        return {}
    links = list(SharedBudgetTransactionLink.objects.filter(shared_budget_id__in=budget_ids).values_list("shared_budget_id", "transaction_id"))
    linked_ids_by_budget: dict[int, set[int]] = defaultdict(set)
    for shared_budget_id, transaction_id in links:
        linked_ids_by_budget[int(shared_budget_id)].add(int(transaction_id))
    attributed_rows = Transaction.objects.filter(shared_budget_id__in=budget_ids).values_list("shared_budget_id", "id")
    attributed_ids_by_budget: dict[int, set[int]] = defaultdict(set)
    for shared_budget_id, transaction_id in attributed_rows:
        attributed_ids_by_budget[int(shared_budget_id)].add(int(transaction_id))
    all_transaction_ids = set().union(*linked_ids_by_budget.values(), *attributed_ids_by_budget.values())
    transactions_by_id = {
        int(tx.pk): tx
        for tx in Transaction.objects.filter(pk__in=all_transaction_ids).only("id", "type", "status", "date", "amount")
    }
    mapping: dict[int, Decimal] = {}
    for budget in shared_budgets:
        period = resolve_budget_period(budget.month)
        total = ZERO
        effective_tx_ids = linked_ids_by_budget.get(int(budget.pk), set()) | attributed_ids_by_budget.get(int(budget.pk), set())
        for transaction_id in effective_tx_ids:
            tx = transactions_by_id.get(transaction_id)
            if not tx:
                continue
            if tx.type != Transaction.Type.EXPENSE:
                continue
            if not is_transaction_countable_for_ledger(tx):
                continue
            if tx.date < period.start or tx.date >= period.end_exclusive:
                continue
            total += _quantize(tx.amount)
        budget._linked_transactions_count = len(effective_tx_ids)
        mapping[int(budget.pk)] = _quantize(total)
    return mapping


def _shared_committed_spent_map(shared_budgets: list[SharedBudget]) -> dict[int, Decimal]:
    budget_ids = [budget.pk for budget in shared_budgets]
    if not budget_ids:
        return {}
    links = list(SharedBudgetTemplateLink.objects.filter(shared_budget_id__in=budget_ids).values_list("shared_budget_id", "payment_template_id"))
    linked_template_ids_by_budget: dict[int, set[int]] = defaultdict(set)
    for shared_budget_id, template_id in links:
        linked_template_ids_by_budget[int(shared_budget_id)].add(int(template_id))
    attributed_template_rows = PaymentTemplate.objects.filter(shared_budget_id__in=budget_ids).values_list("shared_budget_id", "id")
    attributed_template_ids_by_budget: dict[int, set[int]] = defaultdict(set)
    for shared_budget_id, template_id in attributed_template_rows:
        attributed_template_ids_by_budget[int(shared_budget_id)].add(int(template_id))
    all_template_ids = set().union(*linked_template_ids_by_budget.values(), *attributed_template_ids_by_budget.values())
    templates_by_id = {
        int(template.pk): template
        for template in PaymentTemplate.objects.filter(pk__in=all_template_ids).only(
            "id", "is_active", "amount_mode", "default_amount", "next_run_at"
        )
    }
    mapping: dict[int, Decimal] = {}
    for budget in shared_budgets:
        period = resolve_budget_period(budget.month)
        total = ZERO
        effective_template_ids = linked_template_ids_by_budget.get(int(budget.pk), set()) | attributed_template_ids_by_budget.get(int(budget.pk), set())
        for template_id in effective_template_ids:
            template = templates_by_id.get(template_id)
            if not template or not template.is_active:
                continue
            if template.amount_mode != PaymentTemplate.AmountMode.FIXED or template.default_amount is None:
                continue
            if not template.next_run_at:
                continue
            run_date = template.next_run_at.date()
            if run_date < period.start or run_date >= period.end_exclusive:
                continue
            total += _quantize(template.default_amount)
        budget._linked_templates_count = len(effective_template_ids)
        mapping[int(budget.pk)] = _quantize(total)
    return mapping


def list_shared_budgets_with_metrics(*, user, month: str | None = None, team_id: int | None = None) -> dict:
    queryset = (
        SharedBudget.objects.filter(
            Q(team__owner=user) | Q(team__memberships__user=user, team__memberships__is_active=True)
        )
        .select_related("team")
        .distinct()
        .order_by("-month", "name")
    )
    normalized_month = normalize_budget_month(month) if month else None
    if normalized_month:
        queryset = queryset.filter(month=normalized_month)
    if team_id:
        queryset = queryset.filter(team_id=team_id)
    budgets = list(queryset)
    actual_map = _shared_actual_spent_map(budgets)
    committed_map = _shared_committed_spent_map(budgets)
    rows = []
    for budget in budgets:
        thresholds = normalize_alert_thresholds(budget.alert_thresholds)
        metrics = _compute_budget_metrics(
            amount=budget.amount,
            actual_spent=actual_map.get(int(budget.pk), ZERO),
            committed_spent=committed_map.get(int(budget.pk), ZERO),
            thresholds=thresholds,
        )
        rows.append(_serialize_shared_budget_row(budget, metrics))
    return {
        "summary": _summarize_rows(rows, scope_type="shared", month=normalized_month),
        "results": rows,
    }


def build_budget_monthly_overview(*, owner, month: str) -> dict:
    user = owner
    period = resolve_budget_period(month)
    personal_payload = list_category_budgets_with_metrics(owner=user, month=period.month)
    shared_payload = list_shared_budgets_with_metrics(user=user, month=period.month)
    return {
        "month": period.month,
        "period_start": period.start.isoformat(),
        "period_end_exclusive": period.end_exclusive.isoformat(),
        "timezone_policy": "Budget month uses backend calendar month; ledger filters run over Transaction.date.",
        "personal_category_budgets": personal_payload["results"],
        "shared_budgets": shared_payload["results"],
        "personal_category_summary": personal_payload["summary"],
        "shared_summary": shared_payload["summary"],
        "notes": [
            "planned es fijo; actual y committed son dinamicos.",
            "committed agrega pagos programados o plantillas futuras del mismo mes.",
            "shared budgets usan linking explicito de transacciones y templates; no intentan inferir gasto grupal automaticamente.",
        ],
    }


def _build_budget_payload(*, budget, scope_type: str) -> dict:
    payload = {
        "budget_id": str(budget.pk),
        "owner_id": str(budget.owner_id),
        "scope_type": scope_type,
        "month": budget.month,
        "amount": str(_quantize(budget.amount)),
        "alert_thresholds": normalize_alert_thresholds(getattr(budget, "alert_thresholds", None)),
    }
    if scope_type == "personal_category":
        payload["category_id"] = str(budget.category_id)
    elif scope_type == "shared":
        payload["team_id"] = str(budget.team_id)
        payload["name"] = budget.name
    return payload


def _publish_budget_write_event(*, budget, scope_type: str, event_type: str, source: str) -> None:
    publish_budget_event_after_commit(
        event_type=event_type,
        aggregate_type=scope_type,
        aggregate_id=budget.pk,
        payload=_build_budget_payload(budget=budget, scope_type=scope_type),
        metadata={"source": source},
        priority=EventPriority.NORMAL,
    )


def _active_budget_alerts(owner, *, budget_key: str | None = None) -> list[Alert]:
    alerts = list(
        Alert.objects.filter(
            owner=owner,
            type=AlertType.OVER_SPEND,
            source=BUDGET_ALERT_SOURCE,
            is_active=True,
        ).order_by("-created_at")
    )
    if budget_key is None:
        return alerts
    return [alert for alert in alerts if (alert.payload or {}).get("budget_key") == budget_key]


def _resolve_threshold_alerts_for_budget_key(*, owner, budget_key: str, keep_thresholds: set[int]) -> None:
    for alert in _active_budget_alerts(owner, budget_key=budget_key):
        threshold = int((alert.payload or {}).get("threshold_percent") or 0)
        if threshold not in keep_thresholds:
            alert.mark_resolved(commit=True)


def _sync_threshold_alerts_for_row(*, owner, row: dict) -> None:
    budget_key = f"{row['scope_type']}:{row['id']}:{row['month']}"
    thresholds = set(int(value) for value in row["metrics"]["triggered_thresholds"])
    existing = _active_budget_alerts(owner, budget_key=budget_key)
    existing_by_threshold = {
        int((alert.payload or {}).get("threshold_percent") or 0): alert
        for alert in existing
    }
    for threshold in thresholds:
        if threshold in existing_by_threshold:
            continue
        metrics = row["metrics"]
        severity = AlertSeverity.CRITICAL if threshold >= 100 or metrics["is_exceeded"] else AlertSeverity.WARNING
        target = row.get("category", {}).get("name") or row.get("name") or row.get("team", {}).get("name") or "presupuesto"
        create_alert(
            owner=owner,
            type=AlertType.OVER_SPEND,
            title="Tu presupuesto cruzo un umbral",
            message=(
                f"El presupuesto '{target}' alcanzo el {threshold}% en {row['month']} "
                f"({metrics['actual_percentage_used']}% ejecutado, {metrics['projected_percentage_used']}% proyectado)."
            ),
            category=AlertCategory.SPENDING,
            severity=severity,
            payload={
                "budget_key": budget_key,
                "budget_kind": row["scope_type"],
                "budget_id": row["id"],
                "month": row["month"],
                "threshold_percent": threshold,
                "alert_state": metrics["alert_state"],
                "planned_amount": row["amount"],
                "actual_spent": metrics["actual_spent"],
                "committed_spent": metrics["committed_spent"],
                "projected_spent": metrics["projected_spent"],
                "actual_percentage_used": metrics["actual_percentage_used"],
                "projected_percentage_used": metrics["projected_percentage_used"],
                "category_id": row.get("category", {}).get("id"),
                "team_id": row.get("team", {}).get("id"),
            },
            source=BUDGET_ALERT_SOURCE,
            correlation_id=f"{budget_key}:{threshold}",
        )
    _resolve_threshold_alerts_for_budget_key(owner=owner, budget_key=budget_key, keep_thresholds=thresholds)


def _resolve_all_budget_alerts_for_budget_key(*, owner, budget_key: str) -> None:
    _resolve_threshold_alerts_for_budget_key(owner=owner, budget_key=budget_key, keep_thresholds=set())


def evaluate_personal_budget_thresholds_for_user_month(*, user, month: str, source: str) -> dict:
    payload = list_category_budgets_with_metrics(owner=user, month=month)
    for row in payload["results"]:
        _sync_threshold_alerts_for_row(owner=user, row=row)
    logger.debug("[budgets] evaluated personal thresholds user=%s month=%s source=%s", user.pk, month, source)
    return payload


def evaluate_shared_budget_thresholds_for_budget_ids(*, budget_ids: list[int], source: str) -> list[dict]:
    budgets = list(SharedBudget.objects.filter(pk__in=budget_ids).select_related("team"))
    if not budgets:
        return []
    actual_map = _shared_actual_spent_map(budgets)
    committed_map = _shared_committed_spent_map(budgets)
    rows = []
    for budget in budgets:
        thresholds = normalize_alert_thresholds(budget.alert_thresholds)
        metrics = _compute_budget_metrics(
            amount=budget.amount,
            actual_spent=actual_map.get(int(budget.pk), ZERO),
            committed_spent=committed_map.get(int(budget.pk), ZERO),
            thresholds=thresholds,
        )
        row = _serialize_shared_budget_row(budget, metrics)
        rows.append(row)
        _sync_threshold_alerts_for_row(owner=budget.owner, row=row)
    logger.debug("[budgets] evaluated shared thresholds budgets=%s source=%s", budget_ids, source)
    return rows


def evaluate_budget_thresholds_for_owner_month(*, owner, month: str) -> dict:
    evaluate_personal_budget_thresholds_for_user_month(user=owner, month=month, source="finance.budgets.services")
    shared_payload = list_shared_budgets_with_metrics(user=owner, month=month)
    for row in shared_payload["results"]:
        _sync_threshold_alerts_for_row(owner=owner, row=row)
    return build_budget_monthly_overview(owner=owner, month=month)


def evaluate_budget_thresholds_for_owner_month_by_id(*, owner_id, month: str, source: str) -> dict | None:
    owner = User.objects.filter(pk=owner_id).first()
    if not owner:
        return None
    return evaluate_personal_budget_thresholds_for_user_month(user=owner, month=month, source=source)


def get_category_budget_detail(*, owner, budget_id: int) -> dict:
    budget = Budget.objects.filter(owner=owner, pk=budget_id).select_related("category").first()
    if not budget:
        raise PermissionDenied("No puedes ver este presupuesto.")
    actual_map = _personal_actual_spent_map(owner, [budget])
    committed_map = _personal_committed_spent_map(owner, [budget])
    metrics = _compute_budget_metrics(
        amount=budget.amount,
        actual_spent=actual_map.get((budget.month, int(budget.category_id)), ZERO),
        committed_spent=committed_map.get((budget.month, int(budget.category_id)), ZERO),
        thresholds=normalize_alert_thresholds(budget.alert_thresholds),
    )
    return _serialize_category_budget_row(budget, metrics)


def create_category_budget(*, owner, month, category_id, amount, alert_thresholds=None, source: str = "finance.budgets.api") -> dict:
    normalized_month = normalize_budget_month(month)
    category = _load_expense_category_for_owner(owner, category_id)
    amount_value = _validate_amount(amount)
    thresholds = normalize_alert_thresholds(alert_thresholds)
    if Budget.objects.filter(owner=owner, month=normalized_month, category=category).exists():
        raise ValidationError({"non_field_errors": ["Ya existe un presupuesto de categoria para ese periodo y categoria."]})

    with transaction.atomic():
        budget = Budget.objects.create(
            owner=owner,
            month=normalized_month,
            category=category,
            amount=amount_value,
            alert_thresholds=thresholds,
        )
        _publish_budget_write_event(
            budget=budget,
            scope_type="personal_category",
            event_type=BudgetDomainEventTypes.BUDGET_CREATED,
            source=source,
        )
    evaluate_personal_budget_thresholds_for_user_month(user=owner, month=normalized_month, source=source)
    return get_category_budget_detail(owner=owner, budget_id=budget.pk)


def update_category_budget(
    *,
    owner,
    budget_id: int,
    month=None,
    category_id=None,
    amount=None,
    alert_thresholds=None,
    source: str = "finance.budgets.api",
) -> dict:
    budget = Budget.objects.filter(owner=owner, pk=budget_id).select_related("category").first()
    if not budget:
        raise PermissionDenied("No puedes operar este presupuesto.")
    normalized_month = normalize_budget_month(month or budget.month)
    category = _load_expense_category_for_owner(owner, category_id or budget.category_id)
    amount_value = _validate_amount(amount if amount is not None else budget.amount)
    thresholds = normalize_alert_thresholds(alert_thresholds if alert_thresholds is not None else budget.alert_thresholds)
    duplicate = Budget.objects.filter(owner=owner, month=normalized_month, category=category).exclude(pk=budget.pk).exists()
    if duplicate:
        raise ValidationError({"non_field_errors": ["Ya existe otro presupuesto de categoria para ese periodo y categoria."]})

    with transaction.atomic():
        budget.month = normalized_month
        budget.category = category
        budget.amount = amount_value
        budget.alert_thresholds = thresholds
        budget.save(update_fields=["month", "category", "amount", "alert_thresholds"])
        _publish_budget_write_event(
            budget=budget,
            scope_type="personal_category",
            event_type=BudgetDomainEventTypes.BUDGET_UPDATED,
            source=source,
        )
    evaluate_personal_budget_thresholds_for_user_month(user=owner, month=normalized_month, source=source)
    return get_category_budget_detail(owner=owner, budget_id=budget.pk)


def delete_category_budget(*, owner, budget_id: int, source: str = "finance.budgets.api") -> None:
    budget = Budget.objects.filter(owner=owner, pk=budget_id).select_related("category").first()
    if not budget:
        raise PermissionDenied("No puedes operar este presupuesto.")
    budget_key = f"personal_category:{budget.pk}:{budget.month}"
    month = budget.month
    payload = _build_budget_payload(budget=budget, scope_type="personal_category")
    with transaction.atomic():
        budget.delete()
        publish_budget_event_after_commit(
            event_type=BudgetDomainEventTypes.BUDGET_DELETED,
            aggregate_type="personal_category",
            aggregate_id=payload["budget_id"],
            payload=payload,
            metadata={"source": source},
            priority=EventPriority.NORMAL,
        )
    _resolve_all_budget_alerts_for_budget_key(owner=owner, budget_key=budget_key)
    evaluate_personal_budget_thresholds_for_user_month(user=owner, month=month, source=source)


def merge_category_budget_period(*, owner, month, items: list[dict], source: str = "finance.budgets.api") -> dict:
    normalized_month = normalize_budget_month(month)
    payloads: dict[int, tuple[Category, Decimal, list[int]]] = {}
    for item in items:
        category = _load_expense_category_for_owner(owner, item.get("category"))
        amount_value = _validate_amount(item.get("amount"))
        thresholds = normalize_alert_thresholds(item.get("alert_thresholds"))
        if category.pk in payloads:
            raise ValidationError({"items": "No puedes repetir la misma categoria dentro de la misma operacion."})
        payloads[int(category.pk)] = (category, amount_value, thresholds)

    with transaction.atomic():
        for category, amount_value, thresholds in payloads.values():
            budget, created = Budget.objects.get_or_create(
                owner=owner,
                month=normalized_month,
                category=category,
                defaults={"amount": amount_value, "alert_thresholds": thresholds},
            )
            if created:
                _publish_budget_write_event(
                    budget=budget,
                    scope_type="personal_category",
                    event_type=BudgetDomainEventTypes.BUDGET_CREATED,
                    source=source,
                )
            else:
                changed = False
                if _quantize(budget.amount) != amount_value:
                    budget.amount = amount_value
                    changed = True
                if normalize_alert_thresholds(budget.alert_thresholds) != thresholds:
                    budget.alert_thresholds = thresholds
                    changed = True
                if changed:
                    budget.save(update_fields=["amount", "alert_thresholds"])
                    _publish_budget_write_event(
                        budget=budget,
                        scope_type="personal_category",
                        event_type=BudgetDomainEventTypes.BUDGET_UPDATED,
                        source=source,
                    )
    evaluate_personal_budget_thresholds_for_user_month(user=owner, month=normalized_month, source=source)
    return list_category_budgets_with_metrics(owner=owner, month=normalized_month)


def replace_category_budget_period(*, owner, month, items: list[dict], source: str = "finance.budgets.api") -> dict:
    normalized_month = normalize_budget_month(month)
    merge_category_budget_period(owner=owner, month=normalized_month, items=items, source=source)
    keep_category_ids = {int(item.get("category")) for item in items}
    stale_budgets = list(Budget.objects.filter(owner=owner, month=normalized_month).exclude(category_id__in=keep_category_ids))
    with transaction.atomic():
        for budget in stale_budgets:
            deleted_payload = _build_budget_payload(budget=budget, scope_type="personal_category")
            budget_key = f"personal_category:{budget.pk}:{budget.month}"
            budget.delete()
            _resolve_all_budget_alerts_for_budget_key(owner=owner, budget_key=budget_key)
            publish_budget_event_after_commit(
                event_type=BudgetDomainEventTypes.BUDGET_DELETED,
                aggregate_type="personal_category",
                aggregate_id=deleted_payload["budget_id"],
                payload=deleted_payload,
                metadata={"source": source},
                priority=EventPriority.NORMAL,
            )
    evaluate_personal_budget_thresholds_for_user_month(user=owner, month=normalized_month, source=source)
    return list_category_budgets_with_metrics(owner=owner, month=normalized_month)


def get_shared_budget_detail(*, user, budget_id: int) -> dict:
    budget = _load_visible_shared_budget(user, budget_id)
    actual_map = _shared_actual_spent_map([budget])
    committed_map = _shared_committed_spent_map([budget])
    metrics = _compute_budget_metrics(
        amount=budget.amount,
        actual_spent=actual_map.get(int(budget.pk), ZERO),
        committed_spent=committed_map.get(int(budget.pk), ZERO),
        thresholds=normalize_alert_thresholds(budget.alert_thresholds),
    )
    return _serialize_shared_budget_row(budget, metrics)


def create_shared_budget(*, user, team, name, month, amount, alert_thresholds=None, notes="", source: str = "finance.budgets.api") -> dict:
    team_obj = _load_manageable_team(user, team)
    normalized_month = normalize_budget_month(month)
    amount_value = _validate_amount(amount)
    thresholds = normalize_alert_thresholds(alert_thresholds)
    if SharedBudget.objects.filter(team=team_obj, month=normalized_month, name=str(name or "").strip()).exists():
        raise ValidationError({"non_field_errors": ["Ya existe un presupuesto compartido con ese nombre y periodo dentro del equipo."]})

    with transaction.atomic():
        budget = SharedBudget.objects.create(
            owner=team_obj.owner,
            team=team_obj,
            name=str(name or "").strip(),
            month=normalized_month,
            amount=amount_value,
            alert_thresholds=thresholds,
            notes=str(notes or "").strip(),
        )
        _publish_budget_write_event(
            budget=budget,
            scope_type="shared",
            event_type=BudgetDomainEventTypes.BUDGET_CREATED,
            source=source,
        )
    evaluate_shared_budget_thresholds_for_budget_ids(budget_ids=[budget.pk], source=source)
    return get_shared_budget_detail(user=user, budget_id=budget.pk)


def update_shared_budget(
    *,
    user,
    budget_id: int,
    name=None,
    month=None,
    amount=None,
    alert_thresholds=None,
    notes=None,
    source: str = "finance.budgets.api",
) -> dict:
    budget = _load_visible_shared_budget(user, budget_id)
    _assert_can_manage_team_budget(user, budget.team)
    normalized_month = normalize_budget_month(month or budget.month)
    amount_value = _validate_amount(amount if amount is not None else budget.amount)
    thresholds = normalize_alert_thresholds(alert_thresholds if alert_thresholds is not None else budget.alert_thresholds)
    resolved_name = str(name if name is not None else budget.name).strip()
    resolved_notes = str(notes if notes is not None else budget.notes).strip()
    duplicate = SharedBudget.objects.filter(team=budget.team, month=normalized_month, name=resolved_name).exclude(pk=budget.pk).exists()
    if duplicate:
        raise ValidationError({"non_field_errors": ["Ya existe otro presupuesto compartido con ese nombre y periodo dentro del equipo."]})
    with transaction.atomic():
        budget.name = resolved_name
        budget.month = normalized_month
        budget.amount = amount_value
        budget.alert_thresholds = thresholds
        budget.notes = resolved_notes
        budget.save(update_fields=["name", "month", "amount", "alert_thresholds", "notes", "updated_at"])
        _publish_budget_write_event(
            budget=budget,
            scope_type="shared",
            event_type=BudgetDomainEventTypes.BUDGET_UPDATED,
            source=source,
        )
    evaluate_shared_budget_thresholds_for_budget_ids(budget_ids=[budget.pk], source=source)
    return get_shared_budget_detail(user=user, budget_id=budget.pk)


def delete_shared_budget(*, user, budget_id: int, source: str = "finance.budgets.api") -> None:
    budget = _load_visible_shared_budget(user, budget_id)
    _assert_can_manage_team_budget(user, budget.team)
    budget_key = f"shared:{budget.pk}:{budget.month}"
    payload = _build_budget_payload(budget=budget, scope_type="shared")
    owner = budget.owner
    with transaction.atomic():
        budget.delete()
        publish_budget_event_after_commit(
            event_type=BudgetDomainEventTypes.BUDGET_DELETED,
            aggregate_type="shared",
            aggregate_id=payload["budget_id"],
            payload=payload,
            metadata={"source": source},
            priority=EventPriority.NORMAL,
        )
    _resolve_all_budget_alerts_for_budget_key(owner=owner, budget_key=budget_key)


def link_transaction_to_shared_budget(*, user, budget_id: int, transaction_id: int, source: str = "finance.budgets.api") -> dict:
    budget = _load_visible_shared_budget(user, budget_id)
    _assert_can_manage_team_budget(user, budget.team)
    tx = _validate_transaction_for_shared_budget(budget, transaction_id)
    SharedBudgetTransactionLink.objects.get_or_create(
        shared_budget=budget,
        transaction=tx,
        defaults={"linked_by": user},
    )
    tx.budget_scope = BudgetScope.SHARED
    tx.shared_budget = budget
    tx.budget_attribution_source = BudgetAttributionSource.LINKED_AFTER_CREATION
    tx._event_actor_id = str(user.id)
    tx.save(update_fields=["budget_scope", "shared_budget", "budget_attribution_source", "updated_at"])
    evaluate_shared_budget_thresholds_for_budget_ids(budget_ids=[budget.pk], source=source)
    return get_shared_budget_detail(user=user, budget_id=budget.pk)


def unlink_transaction_from_shared_budget(*, user, budget_id: int, transaction_id: int, source: str = "finance.budgets.api") -> dict:
    budget = _load_visible_shared_budget(user, budget_id)
    _assert_can_manage_team_budget(user, budget.team)
    tx = Transaction.objects.filter(pk=transaction_id).first()
    SharedBudgetTransactionLink.objects.filter(shared_budget=budget, transaction_id=transaction_id).delete()
    if tx and tx.shared_budget_id == budget.pk:
        tx.budget_scope = BudgetScope.PERSONAL
        tx.shared_budget = None
        tx.budget_attribution_source = BudgetAttributionSource.LINKED_AFTER_CREATION
        tx._event_actor_id = str(user.id)
        tx.save(update_fields=["budget_scope", "shared_budget", "budget_attribution_source", "updated_at"])
    evaluate_shared_budget_thresholds_for_budget_ids(budget_ids=[budget.pk], source=source)
    return get_shared_budget_detail(user=user, budget_id=budget.pk)


def link_template_to_shared_budget(*, user, budget_id: int, payment_template_id: int, source: str = "finance.budgets.api") -> dict:
    budget = _load_visible_shared_budget(user, budget_id)
    _assert_can_manage_team_budget(user, budget.team)
    template = _validate_payment_template_for_shared_budget(budget, payment_template_id)
    SharedBudgetTemplateLink.objects.get_or_create(
        shared_budget=budget,
        payment_template=template,
        defaults={"linked_by": user},
    )
    from payments.scheduled_payments.services import update_payment_template

    update_payment_template(
        template,
        budget_scope=BudgetScope.SHARED,
        shared_budget=budget,
        budget_attribution_source=BudgetAttributionSource.LINKED_AFTER_CREATION,
    )
    evaluate_shared_budget_thresholds_for_budget_ids(budget_ids=[budget.pk], source=source)
    return get_shared_budget_detail(user=user, budget_id=budget.pk)


def unlink_template_from_shared_budget(*, user, budget_id: int, payment_template_id: int, source: str = "finance.budgets.api") -> dict:
    budget = _load_visible_shared_budget(user, budget_id)
    _assert_can_manage_team_budget(user, budget.team)
    template = PaymentTemplate.objects.filter(pk=payment_template_id).first()
    SharedBudgetTemplateLink.objects.filter(shared_budget=budget, payment_template_id=payment_template_id).delete()
    if template and template.shared_budget_id == budget.pk:
        from payments.scheduled_payments.services import update_payment_template

        update_payment_template(
            template,
            budget_scope=BudgetScope.PERSONAL,
            shared_budget=None,
            budget_attribution_source=BudgetAttributionSource.LINKED_AFTER_CREATION,
        )
    evaluate_shared_budget_thresholds_for_budget_ids(budget_ids=[budget.pk], source=source)
    return get_shared_budget_detail(user=user, budget_id=budget.pk)
