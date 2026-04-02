from __future__ import annotations

from django.utils import timezone

from finance.accounts.models import AccountMembership
from finance.accounts.services.account_invitation_service import issue_membership_invitation
from finance.accounts.services.account_policy_service import (
    validate_account_members_limit,
    validate_account_membership_payload as policy_validate_account_membership_payload,
)


def validate_account_membership_payload(*, attrs, instance=None):
    return policy_validate_account_membership_payload(attrs=attrs, instance=instance)


def create_account_membership(*, validated_data, request_user=None):
    send_invitation = validated_data.pop("send_invitation", True)
    invitation_ttl_days = validated_data.pop("invitation_ttl_days", 14)
    invitation_channel = validated_data.pop("invitation_channel", "direct_link")
    invitation_metadata = validated_data.pop("invitation_metadata", {})
    if validated_data.get("invited_by") is None and request_user is not None:
        validated_data["invited_by"] = request_user

    validate_account_members_limit(account=validated_data["account"])
    membership = AccountMembership(**validated_data)
    membership.full_clean()
    membership.save()
    if not membership.is_active and send_invitation:
        issue_membership_invitation(
            membership=membership,
            invited_by=validated_data.get("invited_by"),
            sent_at=membership.invitation_sent_at or timezone.now(),
            ttl_days=invitation_ttl_days,
            channel=invitation_channel,
            metadata=invitation_metadata,
        )
    return membership


def update_account_membership(*, instance, validated_data):
    validated_data.pop("send_invitation", None)
    validated_data.pop("invitation_ttl_days", None)
    validated_data.pop("invitation_channel", None)
    validated_data.pop("invitation_metadata", None)
    for field, value in validated_data.items():
        setattr(instance, field, value)
    instance.full_clean()
    instance.save()
    return instance
