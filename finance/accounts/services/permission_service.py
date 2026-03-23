from __future__ import annotations

from django.db.models import Q

from finance.accounts.domain.enums import AccountAccessMode, AccountMembershipRole


ROLE_WEIGHT = {
    AccountMembershipRole.VIEWER: 10,
    AccountMembershipRole.MEMBER: 20,
    AccountMembershipRole.ADMIN: 30,
    AccountMembershipRole.OWNER: 40,
}


def user_can_view_account(user, account) -> bool:
    if not user or not user.is_authenticated:
        return False
    if account.owner_id == user.id:
        return True

    return account.memberships.filter(user=user, is_active=True).exists()


def user_can_post_transactions(user, account) -> bool:
    if not user or not user.is_authenticated:
        return False
    if account.owner_id == user.id:
        return not account.read_only

    membership = account.memberships.filter(user=user, is_active=True).first()
    if not membership:
        return False
    if membership.access_mode in (AccountAccessMode.WATCH_ONLY, AccountAccessMode.READ_ONLY):
        return False
    return membership.can_post_transactions


def user_can_manage_members(user, account) -> bool:
    if not user or not user.is_authenticated:
        return False
    if account.owner_id == user.id:
        return True

    membership = account.memberships.filter(user=user, is_active=True).first()
    if not membership:
        return False

    if membership.can_manage_members:
        return True
    return ROLE_WEIGHT.get(membership.role, 0) >= ROLE_WEIGHT[AccountMembershipRole.ADMIN]


def account_scope_for_user(user, queryset):
    """
    Scope de lectura compatible con modelo legacy + memberships.
    """
    if not user or not user.is_authenticated:
        return queryset.none()

    return queryset.filter(
        Q(owner=user)
        | Q(memberships__user=user, memberships__is_active=True)
    ).distinct()
