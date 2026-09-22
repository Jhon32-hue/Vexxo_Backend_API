from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from planning.goals.models import Goal
from planning.shared_goals.models import SharedGoal
from social.teams.models import Membership, Team


def visible_shared_goals(user):
    return (
        SharedGoal.objects.filter(
            Q(team__owner=user) | Q(team__memberships__user=user, team__memberships__is_active=True)
        )
        .select_related("goal", "team", "created_by")
        .distinct()
    )


def _can_manage(team: Team, user) -> bool:
    if team.owner_id == user.id:
        return True
    return Membership.objects.filter(
        team=team,
        user=user,
        is_active=True,
        role__in=["owner", "accountant"],
    ).exists()


@transaction.atomic
def share_goal(*, goal: Goal, team: Team, user, contribution_policy: str) -> tuple[SharedGoal, bool]:
    goal = Goal.objects.select_for_update().get(pk=goal.pk, owner=user)
    if not _can_manage(team, user):
        raise PermissionDenied("No puedes administrar metas en este equipo.")
    shared, created = SharedGoal.objects.get_or_create(
        goal=goal,
        defaults={
            "team": team,
            "created_by": user,
            "contribution_policy": contribution_policy,
        },
    )
    if not created and shared.team_id != team.pk:
        raise ValidationError({"goal": "La meta ya esta compartida con otro equipo."})
    if not created and not shared.is_active:
        shared.is_active = True
        shared.revoked_at = None
        shared.revocation_reason = ""
        shared.contribution_policy = contribution_policy
        shared.save(
            update_fields=[
                "is_active",
                "revoked_at",
                "revocation_reason",
                "contribution_policy",
                "updated_at",
            ]
        )
    return shared, created


@transaction.atomic
def update_shared_goal_policy(*, shared_goal: SharedGoal, user, contribution_policy: str) -> SharedGoal:
    shared_goal = SharedGoal.objects.select_for_update().select_related("team").get(pk=shared_goal.pk)
    if not _can_manage(shared_goal.team, user):
        raise PermissionDenied("No puedes administrar esta meta compartida.")
    shared_goal.contribution_policy = contribution_policy
    shared_goal.save(update_fields=["contribution_policy", "updated_at"])
    return shared_goal


@transaction.atomic
def revoke_shared_goal(*, shared_goal: SharedGoal, user, reason: str) -> SharedGoal:
    shared_goal = SharedGoal.objects.select_for_update().select_related("team").get(pk=shared_goal.pk)
    if not _can_manage(shared_goal.team, user):
        raise PermissionDenied("No puedes administrar esta meta compartida.")
    reason = str(reason or "").strip()
    if len(reason) < 5:
        raise ValidationError({"reason": "Revocar acceso requiere un motivo de al menos 5 caracteres."})
    shared_goal.is_active = False
    shared_goal.revoked_at = timezone.now()
    shared_goal.revocation_reason = reason[:255]
    shared_goal.save(update_fields=["is_active", "revoked_at", "revocation_reason", "updated_at"])
    return shared_goal
