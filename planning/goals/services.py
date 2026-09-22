from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from planning.goals.domain_events import GoalDomainEventTypes
from planning.goals.event_service import enqueue_goal_event
from planning.goals.models import Goal, GoalContribution, GoalMilestone


class GoalLifecycleError(ValueError):
    pass


def _money(value) -> Decimal:
    try:
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise GoalLifecycleError("El valor monetario no es valido.") from exc


def _goal_payload(goal: Goal) -> dict:
    return {
        "goal_id": goal.pk,
        "owner_id": goal.owner_id,
        "status": goal.status,
        "active": goal.active,
        "progress": str(goal.progress),
        "target_amount": str(goal.target_amount),
        "account_id": goal.account_id,
    }


def _shared_goal_allows_contribution(goal: Goal, user) -> bool:
    from planning.shared_goals.models import SharedGoal
    from social.teams.models import Membership

    shared = SharedGoal.objects.filter(goal=goal, is_active=True).select_related("team").first()
    if shared is None:
        return False
    if shared.team.owner_id == user.id:
        return True
    membership = Membership.objects.filter(team=shared.team, user=user, is_active=True).first()
    if membership is None:
        return False
    if shared.contribution_policy == SharedGoal.ContributionPolicy.MANAGERS:
        return membership.role in {"owner", "accountant"}
    return True


def _shared_goal_is_visible(goal: Goal, user) -> bool:
    from planning.shared_goals.models import SharedGoal
    from social.teams.models import Membership

    shared = SharedGoal.objects.filter(goal=goal, is_active=True).select_related("team").first()
    if shared is None:
        return False
    return shared.team.owner_id == user.id or Membership.objects.filter(
        team=shared.team,
        user=user,
        is_active=True,
    ).exists()


def _sync_goal_milestones(goal: Goal) -> None:
    now = timezone.now()
    for milestone in GoalMilestone.objects.select_for_update().filter(goal=goal):
        achieved = goal.progress >= milestone.target_amount
        if achieved and milestone.achieved_at is None:
            milestone.achieved_at = now
            milestone.save(update_fields=["achieved_at"])
            enqueue_goal_event(
                event_type=GoalDomainEventTypes.MILESTONE_ACHIEVED,
                aggregate_type="goal_milestone",
                aggregate_id=milestone.pk,
                payload={
                    "goal_id": goal.pk,
                    "milestone_id": milestone.pk,
                    "target_amount": str(milestone.target_amount),
                    "progress": str(goal.progress),
                },
            )
        elif not achieved and milestone.achieved_at is not None:
            milestone.achieved_at = None
            milestone.save(update_fields=["achieved_at"])
            enqueue_goal_event(
                event_type=GoalDomainEventTypes.MILESTONE_REOPENED,
                aggregate_type="goal_milestone",
                aggregate_id=milestone.pk,
                payload={
                    "goal_id": goal.pk,
                    "milestone_id": milestone.pk,
                    "target_amount": str(milestone.target_amount),
                    "progress": str(goal.progress),
                },
            )


def _set_goal_status(goal: Goal, status: str) -> list[str]:
    changed = []
    active = status == Goal.Status.ACTIVE
    completed_at = goal.completed_at
    if status == Goal.Status.COMPLETED:
        completed_at = completed_at or timezone.now()
    elif goal.status == Goal.Status.COMPLETED:
        completed_at = None
    if goal.status != status:
        goal.status = status
        changed.append("status")
    if goal.active != active:
        goal.active = active
        changed.append("active")
    if goal.completed_at != completed_at:
        goal.completed_at = completed_at
        changed.append("completed_at")
    return changed


def _recalculate_goal_progress(goal: Goal, *, emit_event: bool = True) -> Goal:
    total = (
        GoalContribution.objects.filter(goal=goal, reversed_at__isnull=True).aggregate(total=Sum("amount"))[
            "total"
        ]
        or Decimal("0.00")
    )
    total = _money(total)
    previous_progress = goal.progress
    previous_status = goal.status
    changed = []
    if goal.progress != total:
        goal.progress = total
        changed.append("progress")

    if goal.status not in {Goal.Status.PAUSED, Goal.Status.CANCELED}:
        target_status = Goal.Status.COMPLETED if total >= goal.target_amount else Goal.Status.ACTIVE
        changed.extend(_set_goal_status(goal, target_status))
    if changed:
        goal.save(update_fields=[*sorted(set(changed)), "updated_at"])
    _sync_goal_milestones(goal)

    if emit_event and previous_progress != goal.progress:
        enqueue_goal_event(
            event_type=GoalDomainEventTypes.PROGRESS_UPDATED,
            aggregate_type="goal",
            aggregate_id=goal.pk,
            payload={
                **_goal_payload(goal),
                "previous_progress": str(previous_progress),
            },
        )
    if emit_event and previous_status != goal.status:
        enqueue_goal_event(
            event_type=GoalDomainEventTypes.STATUS_CHANGED,
            aggregate_type="goal",
            aggregate_id=goal.pk,
            payload={**_goal_payload(goal), "previous_status": previous_status},
        )
    return goal


@transaction.atomic
def create_goal(*, owner, **validated_data) -> Goal:
    validated_data = dict(validated_data)
    for protected in (
        "owner",
        "progress",
        "status",
        "active",
        "completed_at",
        "created_at",
        "updated_at",
    ):
        validated_data.pop(protected, None)
    target_amount = _money(validated_data.get("target_amount"))
    if target_amount <= 0:
        raise GoalLifecycleError("El objetivo debe ser mayor que cero.")
    account = validated_data.get("account")
    if account is not None and account.owner_id != owner.id:
        raise GoalLifecycleError("La cuenta no pertenece al usuario autenticado.")
    goal = Goal.objects.create(
        owner=owner,
        target_amount=target_amount,
        progress=Decimal("0.00"),
        status=Goal.Status.ACTIVE,
        active=True,
        **{key: value for key, value in validated_data.items() if key != "target_amount"},
    )
    enqueue_goal_event(
        event_type=GoalDomainEventTypes.GOAL_CREATED,
        aggregate_type="goal",
        aggregate_id=goal.pk,
        payload=_goal_payload(goal),
    )
    return goal


@transaction.atomic
def update_goal(*, goal: Goal, owner, changes: dict) -> Goal:
    goal = Goal.objects.select_for_update().get(pk=goal.pk, owner=owner)
    changes = dict(changes)
    for protected in (
        "owner",
        "progress",
        "status",
        "active",
        "completed_at",
        "created_at",
        "updated_at",
    ):
        changes.pop(protected, None)
    if "target_amount" in changes:
        changes["target_amount"] = _money(changes["target_amount"])
        if changes["target_amount"] <= 0:
            raise GoalLifecycleError("El objetivo debe ser mayor que cero.")
    account = changes.get("account", goal.account)
    if account is not None and account.owner_id != owner.id:
        raise GoalLifecycleError("La cuenta no pertenece al usuario autenticado.")

    changed_fields = []
    for field, value in changes.items():
        if getattr(goal, field) != value:
            setattr(goal, field, value)
            changed_fields.append(field)
    if changed_fields:
        goal.save(update_fields=[*changed_fields, "updated_at"])
    goal = _recalculate_goal_progress(goal)
    enqueue_goal_event(
        event_type=GoalDomainEventTypes.GOAL_UPDATED,
        aggregate_type="goal",
        aggregate_id=goal.pk,
        payload={**_goal_payload(goal), "changed_fields": sorted(changed_fields)},
    )
    return goal


@transaction.atomic
def change_goal_status(*, goal: Goal, owner, target_status: str, reason: str = "") -> Goal:
    goal = Goal.objects.select_for_update().get(pk=goal.pk, owner=owner)
    if target_status not in {Goal.Status.ACTIVE, Goal.Status.PAUSED, Goal.Status.CANCELED}:
        raise GoalLifecycleError("La transicion solicitada no es valida.")
    if goal.status == Goal.Status.COMPLETED and target_status != Goal.Status.CANCELED:
        raise GoalLifecycleError("Una meta completada solo se reabre al revertir un aporte.")
    if target_status == Goal.Status.CANCELED and len((reason or "").strip()) < 5:
        raise GoalLifecycleError("Cancelar una meta requiere un motivo de al menos 5 caracteres.")
    previous = goal.status
    resolved_status = (
        Goal.Status.COMPLETED
        if target_status == Goal.Status.ACTIVE and goal.progress >= goal.target_amount
        else target_status
    )
    changed = _set_goal_status(goal, resolved_status)
    if changed:
        goal.save(update_fields=[*changed, "updated_at"])
        enqueue_goal_event(
            event_type=GoalDomainEventTypes.STATUS_CHANGED,
            aggregate_type="goal",
            aggregate_id=goal.pk,
            payload={
                **_goal_payload(goal),
                "previous_status": previous,
                "reason": (reason or "")[:255],
            },
        )
    return goal


@transaction.atomic
def record_goal_contribution(
    *,
    goal: Goal,
    owner,
    amount,
    contributed_on,
    idempotency_key: str,
    account=None,
    transaction_obj=None,
    note: str = "",
) -> tuple[GoalContribution, bool]:
    goal = Goal.objects.select_for_update().get(pk=goal.pk)
    is_goal_owner = goal.owner_id == owner.id
    if not is_goal_owner and not _shared_goal_allows_contribution(goal, owner):
        raise GoalLifecycleError("No tienes permiso para aportar a esta meta.")
    amount = _money(amount)
    if amount <= 0:
        raise GoalLifecycleError("El aporte debe ser mayor que cero.")
    idempotency_key = (idempotency_key or "").strip()
    if not 8 <= len(idempotency_key) <= 160:
        raise GoalLifecycleError("Idempotency-Key debe tener entre 8 y 160 caracteres.")
    account = account or (goal.account if is_goal_owner else None)
    if account is not None and account.owner_id != owner.id:
        raise GoalLifecycleError("La cuenta no pertenece al usuario autenticado.")
    if is_goal_owner and goal.account_id and account is not None and account.pk != goal.account_id:
        raise GoalLifecycleError("El aporte debe usar la cuenta vinculada a la meta.")
    if transaction_obj is not None:
        if transaction_obj.owner_id != owner.id:
            raise GoalLifecycleError("La transaccion no pertenece al usuario autenticado.")
        if account is not None and transaction_obj.account_id != account.pk:
            raise GoalLifecycleError("La transaccion y el aporte deben usar la misma cuenta.")

    existing = GoalContribution.objects.filter(owner=owner, idempotency_key=idempotency_key).first()
    if existing is not None:
        same_request = (
            existing.goal_id == goal.pk
            and existing.amount == amount
            and existing.contributed_on == contributed_on
            and existing.account_id == getattr(account, "pk", None)
            and existing.transaction_id == getattr(transaction_obj, "pk", None)
        )
        if not same_request:
            raise GoalLifecycleError("Idempotency-Key ya fue usado con otro aporte.")
        return existing, False

    if goal.status != Goal.Status.ACTIVE:
        raise GoalLifecycleError("Solo se pueden registrar aportes en metas activas.")

    source = GoalContribution.Source.TRANSACTION if transaction_obj else GoalContribution.Source.MANUAL
    contribution = GoalContribution.objects.create(
        owner=owner,
        goal=goal,
        account=account,
        transaction=transaction_obj,
        amount=amount,
        contributed_on=contributed_on,
        source=source,
        note=(note or "")[:255],
        idempotency_key=idempotency_key,
    )
    enqueue_goal_event(
        event_type=GoalDomainEventTypes.CONTRIBUTION_RECORDED,
        aggregate_type="goal_contribution",
        aggregate_id=contribution.pk,
        payload={
            "contribution_id": contribution.pk,
            "goal_id": goal.pk,
            "owner_id": owner.id,
            "amount": str(amount),
            "source": source,
            "transaction_id": contribution.transaction_id,
        },
        correlation_id=str(contribution.transaction_id or ""),
        idempotency_key=f"goal-contribution:{owner.id}:{idempotency_key}",
    )
    _recalculate_goal_progress(goal)
    return contribution, True


@transaction.atomic
def reverse_goal_contribution(*, contribution: GoalContribution, owner, reason: str) -> GoalContribution:
    contribution = GoalContribution.objects.select_for_update().select_related("goal").get(
        pk=contribution.pk,
        owner=owner,
    )
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise GoalLifecycleError("La reversion requiere un motivo de al menos 5 caracteres.")
    if contribution.reversed_at:
        return contribution
    contribution.reversed_at = timezone.now()
    contribution.reversal_reason = reason[:255]
    contribution.save(update_fields=["reversed_at", "reversal_reason"])
    enqueue_goal_event(
        event_type=GoalDomainEventTypes.CONTRIBUTION_REVERSED,
        aggregate_type="goal_contribution",
        aggregate_id=contribution.pk,
        payload={
            "contribution_id": contribution.pk,
            "goal_id": contribution.goal_id,
            "owner_id": owner.id,
            "amount": str(contribution.amount),
            "reason": contribution.reversal_reason,
        },
    )
    _recalculate_goal_progress(contribution.goal)
    return contribution


@transaction.atomic
def create_goal_milestone(*, goal: Goal, owner, name: str, target_amount) -> GoalMilestone:
    goal = Goal.objects.select_for_update().get(pk=goal.pk, owner=owner)
    amount = _money(target_amount)
    if amount <= 0 or amount > goal.target_amount:
        raise GoalLifecycleError("El milestone debe ser mayor que cero y no superar el objetivo.")
    milestone = GoalMilestone.objects.create(
        owner=owner,
        goal=goal,
        name=str(name or "").strip()[:120],
        target_amount=amount,
    )
    _sync_goal_milestones(goal)
    return milestone


def build_goal_projection(*, goal: Goal, viewer) -> dict:
    if goal.owner_id != viewer.id and not _shared_goal_is_visible(goal, viewer):
        raise GoalLifecycleError("No tienes permiso para consultar esta proyeccion.")
    contributions = list(
        GoalContribution.objects.filter(goal=goal, reversed_at__isnull=True)
        .order_by("contributed_on", "id")
        .values("amount", "contributed_on")
    )
    today = timezone.localdate()
    remaining = max(_money(goal.target_amount - goal.progress), Decimal("0.00"))
    days_to_target = max((goal.target_date - today).days, 0)
    months_to_target = max(Decimal(days_to_target) / Decimal("30"), Decimal("1"))
    required_monthly = _money(remaining / months_to_target) if remaining else Decimal("0.00")
    if not contributions or goal.progress <= 0:
        return {
            "goal_id": goal.pk,
            "status": "insufficient_history",
            "remaining_amount": str(remaining),
            "required_monthly_contribution": str(required_monthly),
            "projected_completion_date": None,
            "on_track": False,
            "assumptions": ["No hay aportes suficientes para estimar velocidad historica."],
        }
    first_date = contributions[0]["contributed_on"]
    observed_days = max((today - first_date).days + 1, 1)
    observed_total = sum((Decimal(row["amount"]) for row in contributions), Decimal("0"))
    daily_velocity = observed_total / Decimal(observed_days)
    projected_days = 0 if remaining == 0 else int((remaining / daily_velocity).to_integral_value(rounding=ROUND_CEILING))
    projected_date = today + timedelta(days=projected_days)
    return {
        "goal_id": goal.pk,
        "status": "projected",
        "remaining_amount": str(remaining),
        "observed_days": observed_days,
        "observed_contribution_total": str(_money(observed_total)),
        "average_daily_contribution": str(_money(daily_velocity)),
        "required_monthly_contribution": str(required_monthly),
        "projected_completion_date": projected_date.isoformat(),
        "on_track": projected_date <= goal.target_date,
        "assumptions": [
            "La velocidad futura se asume igual al promedio diario historico.",
            "No incluye rendimientos, inflacion ni aportes programados no ejecutados.",
        ],
    }
