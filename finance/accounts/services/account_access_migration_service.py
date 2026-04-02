"""
Migracion final del sharing legacy `AccountAccess` hacia `AccountMembership`.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from finance.accounts.domain.enums import AccountAccessMode, AccountMembershipRole
from finance.accounts.models import AccountAccess, AccountMembership

ROLE_MAPPING = {
    "owner": AccountMembershipRole.OWNER,
    "admin": AccountMembershipRole.ADMIN,
    "contributor": AccountMembershipRole.MEMBER,
    "viewer": AccountMembershipRole.VIEWER,
}


def build_membership_defaults_from_access(access: AccountAccess) -> dict:
    role = ROLE_MAPPING.get(access.role, AccountMembershipRole.VIEWER)
    access_mode = AccountAccessMode.FULL
    if role == AccountMembershipRole.VIEWER:
        access_mode = AccountAccessMode.READ_ONLY
    elif not access.can_spend:
        access_mode = AccountAccessMode.WATCH_ONLY
    return {
        "role": role,
        "access_mode": access_mode,
        "can_post_transactions": bool(access.can_spend),
        "can_manage_members": bool(access.can_invite or role in {AccountMembershipRole.ADMIN, AccountMembershipRole.OWNER}),
        "can_manage_account_settings": bool(access.can_edit_limits or role in {AccountMembershipRole.ADMIN, AccountMembershipRole.OWNER}),
        "can_view_analytics": bool(access.can_view_balance or access.can_view_transactions or role != AccountMembershipRole.VIEWER),
        "invited_by": access.invited_by,
        "accepted_at": access.accepted_at,
        "joined_at": access.accepted_at,
        "revoked_at": access.revoked_at,
        "is_active": access.is_active,
        "metadata": {
            "legacy_source": "AccountAccess",
            "legacy_account_access_id": access.pk,
            "can_export": bool(access.can_export),
            "can_view_balance": bool(access.can_view_balance),
            "can_view_transactions": bool(access.can_view_transactions),
        },
    }


@transaction.atomic
def migrate_account_access_entry(*, access: AccountAccess, deactivate_legacy: bool = False):
    if access.user_id == access.account.owner_id:
        membership = access.account.ensure_owner_membership()
    else:
        defaults = build_membership_defaults_from_access(access)
        membership, created = AccountMembership.objects.get_or_create(
            account=access.account,
            user=access.user,
            defaults=defaults,
        )
        if not created:
            changed = False
            for field, value in defaults.items():
                if field == "metadata":
                    merged = dict(membership.metadata or {})
                    merged.update(value)
                    value = merged
                if getattr(membership, field) != value:
                    setattr(membership, field, value)
                    changed = True
            if changed:
                membership.full_clean()
                membership.save()
    if deactivate_legacy and access.is_active:
        access.is_active = False
        access.revoked_at = access.revoked_at or timezone.now()
        access.save(update_fields=["is_active", "revoked_at"])
    return membership


def migrate_account_access_entries(*, account_id=None, dry_run: bool = False, deactivate_legacy: bool = False) -> dict:
    qs = AccountAccess.objects.select_related("account", "user", "invited_by").all()
    if account_id:
        qs = qs.filter(account_id=account_id)
    total = qs.count()
    migrated = 0
    deactivated = 0
    for access in qs:
        if dry_run:
            migrated += 1
            if deactivate_legacy and access.is_active:
                deactivated += 1
            continue
        migrate_account_access_entry(access=access, deactivate_legacy=deactivate_legacy)
        migrated += 1
        if deactivate_legacy and access.is_active:
            deactivated += 1
    return {
        "total_legacy_entries": total,
        "migrated_entries": migrated,
        "deactivated_legacy_entries": deactivated,
        "dry_run": dry_run,
    }
