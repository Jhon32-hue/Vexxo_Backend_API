from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from notifications.deliveries.services import create_notification_delivery
from social.invitations.models import TeamInvitation
from social.teams.models import Membership, Team


User = get_user_model()
INVITATION_TTL_DAYS = 7


@transaction.atomic
def issue_team_invitation(*, team: Team, invited_by, email: str, role: str, idempotency_key: str) -> TeamInvitation:
    if team.owner_id != invited_by.pk:
        raise PermissionDenied("Solo el propietario puede invitar personas al equipo.")
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise ValidationError({"email": "El email es requerido."})
    if normalized_email == (invited_by.email or "").strip().lower():
        raise ValidationError({"email": "El propietario ya pertenece al equipo."})
    if role not in {"accountant", "viewer"}:
        raise ValidationError({"role": "Rol de invitacion no permitido."})
    normalized_key = (idempotency_key or "").strip()
    if not normalized_key:
        raise ValidationError({"idempotency_key": "Idempotency-Key es requerido."})
    existing = TeamInvitation.objects.filter(invited_by=invited_by, idempotency_key=normalized_key).first()
    if existing is not None:
        return existing

    invited_user = User.objects.filter(email__iexact=normalized_email).first()
    if invited_user and Membership.objects.filter(team=team, user=invited_user, is_active=True).exists():
        raise ValidationError({"email": "La persona ya es miembro activo del equipo."})
    TeamInvitation.objects.filter(
        team=team,
        email=normalized_email,
        status__in=[TeamInvitation.Status.PENDING, TeamInvitation.Status.OPENED],
    ).update(status=TeamInvitation.Status.REVOKED, revoked_at=timezone.now())
    invitation = TeamInvitation.objects.create(
        team=team,
        invited_user=invited_user,
        invited_by=invited_by,
        email=normalized_email,
        role=role,
        idempotency_key=normalized_key,
        expires_at=timezone.now() + timedelta(days=INVITATION_TTL_DAYS),
    )
    team.save(update_fields=["updated_at"])
    if invited_user is not None:
        create_notification_delivery(
            owner=invited_user,
            title="Te invitaron a un equipo",
            message=f"{invited_by.display_name} te invito a {team.name}.",
            event_type="social.team.invitation_issued.v1",
            source="social.invitations",
            payload={"invitation_id": str(invitation.public_id), "team_id": team.pk, "role": role},
            dedupe_key=f"team-invitation:{invitation.pk}",
        )
    return invitation


@transaction.atomic
def mark_team_invitation_opened(*, invitation: TeamInvitation, actor) -> TeamInvitation:
    _assert_invited_actor(invitation=invitation, actor=actor)
    if invitation.status == TeamInvitation.Status.PENDING:
        invitation.status = TeamInvitation.Status.OPENED
        invitation.opened_at = timezone.now()
        invitation.save(update_fields=["status", "opened_at", "updated_at"])
    return invitation


@transaction.atomic
def accept_team_invitation(*, invitation: TeamInvitation, actor) -> TeamInvitation:
    invitation = TeamInvitation.objects.select_for_update().select_related("team").get(pk=invitation.pk)
    _assert_invited_actor(invitation=invitation, actor=actor)
    if invitation.status == TeamInvitation.Status.ACCEPTED:
        return invitation
    if invitation.expires_at <= timezone.now():
        invitation.status = TeamInvitation.Status.EXPIRED
        invitation.save(update_fields=["status", "updated_at"])
        raise ValidationError({"invitation": "La invitacion expiro."})
    if invitation.status not in {TeamInvitation.Status.PENDING, TeamInvitation.Status.OPENED}:
        raise ValidationError({"invitation": "La invitacion ya no esta disponible."})
    Membership.objects.update_or_create(
        team=invitation.team,
        user=actor,
        defaults={"role": invitation.role, "is_active": True},
    )
    now = timezone.now()
    invitation.invited_user = actor
    invitation.status = TeamInvitation.Status.ACCEPTED
    invitation.opened_at = invitation.opened_at or now
    invitation.accepted_at = now
    invitation.save(update_fields=["invited_user", "status", "opened_at", "accepted_at", "updated_at"])
    invitation.team.save(update_fields=["updated_at"])
    create_notification_delivery(
        owner=invitation.invited_by,
        title="Invitacion de equipo aceptada",
        message=f"{actor.display_name} se unio a {invitation.team.name}.",
        event_type="social.team.invitation_accepted.v1",
        source="social.invitations",
        payload={"invitation_id": str(invitation.public_id), "team_id": invitation.team_id},
        dedupe_key=f"team-invitation-accepted:{invitation.pk}",
    )
    return invitation


@transaction.atomic
def revoke_team_invitation(*, invitation: TeamInvitation, actor) -> TeamInvitation:
    if invitation.team.owner_id != actor.pk and invitation.invited_by_id != actor.pk:
        raise PermissionDenied("No puedes revocar esta invitacion.")
    if invitation.status in {TeamInvitation.Status.ACCEPTED, TeamInvitation.Status.EXPIRED}:
        raise ValidationError({"invitation": "La invitacion ya no puede revocarse."})
    if invitation.status != TeamInvitation.Status.REVOKED:
        invitation.status = TeamInvitation.Status.REVOKED
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["status", "revoked_at", "updated_at"])
        invitation.team.save(update_fields=["updated_at"])
    return invitation


def _assert_invited_actor(*, invitation: TeamInvitation, actor) -> None:
    if invitation.invited_user_id and invitation.invited_user_id != actor.pk:
        raise PermissionDenied("Esta invitacion pertenece a otra persona.")
    if (actor.email or "").strip().lower() != invitation.email:
        raise PermissionDenied("Esta invitacion pertenece a otro email.")
