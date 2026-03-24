"""
ViewSet de membresias compartidas de cuentas.

Descripcion general:
- administra invitaciones, accesos y revocaciones de `AccountMembership`
- separa claramente lectura, alta, aceptacion y baja logica

Analisis detallado:
- las membresias son la fuente de verdad para permisos compartidos en Vexxo,
  asi que su API debe ser explicita y auditable
- los managers de una cuenta pueden invitar, editar o revocar accesos
- el usuario invitado puede aceptar su propia membresia y salir de la cuenta

Que se puede hacer despues:
- agregar expiracion de invitaciones o enlaces firmados
- publicar notificaciones de invitacion/revocacion sobre el outbox del dominio
"""

from __future__ import annotations

from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from finance.accounts.domain.events import AccountDomainEventTypes
from finance.accounts.models import AccountMembership
from finance.accounts.serializers import (
    AccountMembershipAcceptSerializer,
    AccountMembershipRevokeSerializer,
    AccountMembershipRotateInvitationSerializer,
    AccountMembershipSerializer,
    AccountMembershipWriteSerializer,
)
from finance.accounts.services.permission_service import account_scope_for_user, user_can_manage_members
from finance.accounts.services.outbox_service import publish_account_membership_event
from support.audit.helpers import audit_log


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "si"}


class AccountMembershipViewSet(viewsets.ModelViewSet):
    """
    API de colaboracion sobre cuentas compartidas.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AccountMembershipSerializer

    def get_queryset(self):
        scoped_accounts = account_scope_for_user(self.request.user, self._account_base_queryset())
        qs = AccountMembership.objects.select_related("account", "account__owner", "user", "invited_by").filter(
            account__in=scoped_accounts
        )

        account_id = self.request.query_params.get("account")
        role = self.request.query_params.get("role")
        active = self.request.query_params.get("active")
        mine = self.request.query_params.get("mine")
        invitation_pending = self.request.query_params.get("invitation_pending")

        if account_id:
            qs = qs.filter(account_id=account_id)
        if role:
            qs = qs.filter(role=role)
        if active is not None:
            qs = qs.filter(is_active=_truthy(active))
        if _truthy(mine):
            qs = qs.filter(user=self.request.user)
        if invitation_pending is not None:
            if _truthy(invitation_pending):
                qs = qs.filter(invitation_sent_at__isnull=False, accepted_at__isnull=True, is_active=False)
            else:
                qs = qs.exclude(invitation_sent_at__isnull=False, accepted_at__isnull=True, is_active=False)

        return qs.order_by("-is_active", "-invitation_sent_at", "user__username")

    def _account_base_queryset(self):
        from finance.accounts.models import Account

        return Account.objects.all()

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return AccountMembershipWriteSerializer
        if self.action == "accept_invitation":
            return AccountMembershipAcceptSerializer
        if self.action == "revoke":
            return AccountMembershipRevokeSerializer
        if self.action == "rotate_invitation":
            return AccountMembershipRotateInvitationSerializer
        return AccountMembershipSerializer

    def _assert_can_manage_membership(self, membership: AccountMembership) -> None:
        if not user_can_manage_members(self.request.user, membership.account):
            raise PermissionDenied("No puedes administrar miembros en esta cuenta.")

    def _audit(self, *, action_name: str, membership: AccountMembership, description: str, metadata: dict | None = None):
        audit_log(
            user=self.request.user,
            module="accounts",
            action=action_name,
            entity="AccountMembership",
            entity_id=membership.id,
            description=description,
            metadata=metadata or {},
            silent=True,
        )

    @transaction.atomic
    def perform_create(self, serializer):
        account = serializer.validated_data["account"]
        if not user_can_manage_members(self.request.user, account):
            raise PermissionDenied("No puedes invitar miembros a esta cuenta.")

        membership = serializer.save()
        self._audit(
            action_name="membership_create",
            membership=membership,
            description=f"Membresia creada para cuenta {membership.account_id}",
            metadata={
                "account_id": membership.account_id,
                "user_id": membership.user_id,
                "role": membership.role,
                "access_mode": membership.access_mode,
            },
        )
        publish_account_membership_event(
            membership=membership,
            event_type=AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_CREATED,
            change="membership_create",
            metadata={"source": "accounts.views.membership_create"},
        )
        if membership.invitation_pending:
            publish_account_membership_event(
                membership=membership,
                event_type=AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_INVITED,
                change="membership_invited",
                metadata={"source": "accounts.views.membership_create"},
            )

    @transaction.atomic
    def perform_update(self, serializer):
        membership = self.get_object()
        self._assert_can_manage_membership(membership)
        updated = serializer.save()
        self._audit(
            action_name="membership_update",
            membership=updated,
            description=f"Membresia actualizada para cuenta {updated.account_id}",
            metadata={"role": updated.role, "access_mode": updated.access_mode, "is_active": updated.is_active},
        )
        publish_account_membership_event(
            membership=updated,
            event_type=AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_UPDATED,
            change="membership_update",
            metadata={"source": "accounts.views.membership_update"},
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        self._assert_can_manage_membership(instance)
        instance.revoke(commit=True)
        self._audit(
            action_name="membership_revoke",
            membership=instance,
            description=f"Membresia revocada para cuenta {instance.account_id}",
        )
        publish_account_membership_event(
            membership=instance,
            event_type=AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_REVOKED,
            change="membership_destroy",
            metadata={"source": "accounts.views.membership_destroy"},
        )

    @action(detail=True, methods=["post"])
    def accept_invitation(self, request, pk=None):
        membership = self.get_object()
        if membership.user_id != request.user.id and not user_can_manage_members(request.user, membership.account):
            raise PermissionDenied("No puedes aceptar esta invitacion.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership.accept(
            accepted_at=serializer.validated_data.get("accepted_at"),
            joined_at=serializer.validated_data.get("joined_at"),
            commit=True,
        )
        self._audit(
            action_name="membership_accept",
            membership=membership,
            description=f"Invitacion aceptada para cuenta {membership.account_id}",
        )
        publish_account_membership_event(
            membership=membership,
            event_type=AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_ACCEPTED,
            change="membership_accept",
            metadata={"source": "accounts.views.membership_accept"},
        )
        return Response(
            AccountMembershipSerializer(membership, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        membership = self.get_object()
        can_revoke = membership.user_id == request.user.id or user_can_manage_members(request.user, membership.account)
        if not can_revoke:
            raise PermissionDenied("No puedes revocar esta membresia.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership.revoke(revoked_at=serializer.validated_data.get("revoked_at"), commit=True)
        self._audit(
            action_name="membership_revoke",
            membership=membership,
            description=f"Membresia revocada en cuenta {membership.account_id}",
        )
        publish_account_membership_event(
            membership=membership,
            event_type=AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_REVOKED,
            change="membership_revoke",
            metadata={"source": "accounts.views.membership_revoke"},
        )
        return Response(
            AccountMembershipSerializer(membership, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def rotate_invitation(self, request, pk=None):
        membership = self.get_object()
        self._assert_can_manage_membership(membership)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership.rotate_invitation_token(
            sent_at=serializer.validated_data.get("sent_at"),
            commit=True,
        )
        self._audit(
            action_name="membership_rotate_invitation",
            membership=membership,
            description=f"Invitacion reemitida para cuenta {membership.account_id}",
        )
        publish_account_membership_event(
            membership=membership,
            event_type=AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_UPDATED,
            change="membership_rotate_invitation",
            metadata={"source": "accounts.views.membership_rotate_invitation"},
        )
        publish_account_membership_event(
            membership=membership,
            event_type=AccountDomainEventTypes.ACCOUNT_MEMBERSHIP_INVITED,
            change="membership_reinvited",
            metadata={"source": "accounts.views.membership_rotate_invitation"},
        )
        return Response(
            AccountMembershipSerializer(membership, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )
