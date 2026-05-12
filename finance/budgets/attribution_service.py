from __future__ import annotations

from rest_framework import serializers

from finance.budgets.attribution import BudgetAttributionSource, BudgetScope
from finance.budgets.models import SharedBudget
from social.teams.models import Membership


def _active_membership(user, team):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return Membership.objects.filter(team=team, user=user, is_active=True).first()


def user_can_reference_shared_budget(user, shared_budget: SharedBudget | None) -> bool:
    if shared_budget is None or not user or not getattr(user, "is_authenticated", False):
        return False
    if shared_budget.team.owner_id == user.id:
        return True
    return bool(_active_membership(user, shared_budget.team))


def assert_shared_budget_access(user, shared_budget: SharedBudget | None, field_name: str = "shared_budget") -> None:
    if shared_budget is None:
        return
    if not user_can_reference_shared_budget(user, shared_budget):
        raise serializers.ValidationError({field_name: "No puedes usar este presupuesto compartido."})


def normalize_budget_scope(raw_scope) -> str:
    scope = str(raw_scope or "").strip().lower()
    if not scope:
        return ""
    valid = {BudgetScope.NONE, BudgetScope.PERSONAL, BudgetScope.SHARED}
    if scope not in valid:
        raise serializers.ValidationError({"budget_scope": "budget_scope debe ser none, personal o shared."})
    return scope


def resolve_budget_attribution(
    *,
    user,
    budget_scope,
    shared_budget,
    budget_context_shared_budget=None,
    current_scope: str = "",
    current_shared_budget=None,
    current_source: str = "",
    expense_expected: bool,
) -> dict:
    explicit_scope = normalize_budget_scope(budget_scope) if budget_scope is not None else None
    explicit_shared_budget = shared_budget is not None
    context_budget = budget_context_shared_budget
    if context_budget is not None:
        assert_shared_budget_access(user, context_budget, field_name="budget_context_shared_budget")
    if shared_budget is not None:
        assert_shared_budget_access(user, shared_budget)

    if not expense_expected:
        return {
            "budget_scope": BudgetScope.NONE,
            "shared_budget": None,
            "budget_attribution_source": "",
        }

    resolved_scope = normalize_budget_scope(current_scope) if current_scope else ""
    resolved_shared_budget = current_shared_budget
    resolved_source = str(current_source or "").strip()

    if explicit_shared_budget:
        resolved_scope = BudgetScope.SHARED
        resolved_shared_budget = shared_budget
        resolved_source = BudgetAttributionSource.MANUAL
    elif context_budget is not None and explicit_scope is None and current_shared_budget is None:
        resolved_scope = BudgetScope.SHARED
        resolved_shared_budget = context_budget
        resolved_source = BudgetAttributionSource.SUGGESTED_RULE

    if explicit_scope is not None:
        if explicit_scope == BudgetScope.NONE:
            resolved_scope = BudgetScope.NONE
            resolved_shared_budget = None
            resolved_source = BudgetAttributionSource.MANUAL
        elif explicit_scope == BudgetScope.PERSONAL:
            resolved_scope = BudgetScope.PERSONAL
            resolved_shared_budget = None
            resolved_source = BudgetAttributionSource.MANUAL
        elif explicit_scope == BudgetScope.SHARED:
            candidate_shared_budget = shared_budget or context_budget or current_shared_budget
            if candidate_shared_budget is None:
                raise serializers.ValidationError({"shared_budget": "Debes indicar el presupuesto compartido cuando budget_scope=shared."})
            assert_shared_budget_access(user, candidate_shared_budget)
            resolved_scope = BudgetScope.SHARED
            resolved_shared_budget = candidate_shared_budget
            resolved_source = (
                BudgetAttributionSource.MANUAL
                if shared_budget is not None
                else BudgetAttributionSource.SUGGESTED_RULE
                if context_budget is not None and current_shared_budget is None
                else resolved_source or BudgetAttributionSource.MANUAL
            )

    if explicit_scope is None and not explicit_shared_budget and context_budget is None and not resolved_scope:
        resolved_scope = BudgetScope.PERSONAL
        resolved_shared_budget = None
        resolved_source = BudgetAttributionSource.SYSTEM_DEFAULT

    if resolved_scope == BudgetScope.SHARED and resolved_shared_budget is None:
        raise serializers.ValidationError({"shared_budget": "Debes indicar un presupuesto compartido valido."})
    if resolved_scope != BudgetScope.SHARED:
        resolved_shared_budget = None
    if resolved_scope in {BudgetScope.NONE, ""}:
        resolved_source = ""

    return {
        "budget_scope": resolved_scope or BudgetScope.PERSONAL,
        "shared_budget": resolved_shared_budget,
        "budget_attribution_source": resolved_source or BudgetAttributionSource.SYSTEM_DEFAULT,
    }


__all__ = [
    "assert_shared_budget_access",
    "normalize_budget_scope",
    "resolve_budget_attribution",
    "user_can_reference_shared_budget",
]
