"""
Casos de uso del ciclo de vida de `AccountInvitation`.

Descripcion general:
- emite, reemite, acepta, expira y revoca invitaciones asociadas a una
  `AccountMembership`

Analisis detallado:
- mantiene sincronizados el nuevo modelo de invitaciones y los campos legacy de
  `AccountMembership` para preservar compatibilidad en la API actual
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from finance.accounts.models import AccountInvitation

DEFAULT_INVITATION_TTL_DAYS = 14


def resolve_invitation_expiration(*, sent_at=None, ttl_days: int = DEFAULT_INVITATION_TTL_DAYS):
    sent_value = sent_at or timezone.now()
    return sent_value + timedelta(days=max(1, int(ttl_days or DEFAULT_INVITATION_TTL_DAYS)))


def sync_membership_invitation_fields(membership, *, invitation=None, commit: bool = True):
    current = invitation
    if current is None:
        current = membership.invitations.filter(is_current=True).order_by("-attempt_number", "-created_at").first()

    membership.invitation_token = current.token if current else membership.invitation_token
    membership.invitation_sent_at = current.sent_at if current else None
    if current and current.status == AccountInvitation.Status.ACCEPTED:
        membership.accepted_at = current.accepted_at or membership.accepted_at
    elif current and current.status in {AccountInvitation.Status.PENDING, AccountInvitation.Status.OPENED}:
        membership.accepted_at = None
    if commit:
        membership.save(update_fields=["invitation_token", "invitation_sent_at", "accepted_at"])
    return membership


@transaction.atomic
def issue_membership_invitation(
    *,
    membership,
    invited_by=None,
    sent_at=None,
    ttl_days: int = DEFAULT_INVITATION_TTL_DAYS,
    channel: str = "direct_link",
    metadata: dict | None = None,
    resend_of=None,
):
    sent_value = sent_at or timezone.now()
    pending_qs = membership.invitations.filter(is_current=True)
    for invitation in pending_qs:
        invitation.revoke(revoked_at=sent_value, commit=True)

    next_attempt = int(
        membership.invitations.order_by("-attempt_number").values_list("attempt_number", flat=True).first() or 0
    ) + 1
    invitation = AccountInvitation.objects.create(
        membership=membership,
        account=membership.account,
        user=membership.user,
        invited_by=invited_by or membership.invited_by,
        resend_of=resend_of,
        status=AccountInvitation.Status.PENDING,
        attempt_number=next_attempt,
        is_current=True,
        channel=(channel or "direct_link")[:32],
        sent_at=sent_value,
        expires_at=resolve_invitation_expiration(sent_at=sent_value, ttl_days=ttl_days),
        metadata=metadata or {},
    )
    membership.invited_by = invitation.invited_by
    membership.is_active = False
    membership.joined_at = None
    membership.revoked_at = None
    membership.invitation_token = invitation.token
    membership.invitation_sent_at = invitation.sent_at
    membership.accepted_at = None
    membership.save(
        update_fields=[
            "invited_by",
            "is_active",
            "joined_at",
            "revoked_at",
            "invitation_token",
            "invitation_sent_at",
            "accepted_at",
        ]
    )
    return invitation


@transaction.atomic
def accept_membership_invitation(*, membership, accepted_at=None, joined_at=None, invitation=None, commit: bool = True):
    invitation = invitation or membership.current_invitation
    accepted_value = accepted_at or timezone.now()
    if invitation is not None:
        invitation.accept(accepted_at=accepted_value, commit=commit)
    membership._apply_accept_state(accepted_at=accepted_value, joined_at=joined_at, commit=commit)
    sync_membership_invitation_fields(membership, invitation=invitation, commit=commit)
    return invitation


@transaction.atomic
def revoke_membership_invitation(*, membership, revoked_at=None, invitation=None, commit: bool = True):
    invitation = invitation or membership.current_invitation
    revoked_value = revoked_at or timezone.now()
    if invitation is not None:
        invitation.revoke(revoked_at=revoked_value, commit=commit)
    membership._apply_revoke_state(revoked_at=revoked_value, commit=commit)
    sync_membership_invitation_fields(membership, invitation=invitation, commit=commit)
    return invitation


def mark_membership_invitation_opened(*, membership, invitation=None, opened_at=None):
    invitation = invitation or membership.current_invitation
    if invitation is None:
        return None
    if invitation.status == invitation.Status.ACCEPTED:
        return invitation
    invitation.mark_opened(opened_at=opened_at, commit=True)
    return invitation
