"""
Serializers para membresias compartidas de cuentas.

Descripcion general:
- modela la capa REST de colaboracion sobre `AccountMembership`
- separa lectura, escritura y acciones de invitacion/aceptacion/revocacion

Analisis detallado:
- las membresias son la fuente moderna de permisos compartidos en Vexxo
- la API debe dejar claro quien entra a una cuenta, con que rol y por que
  flujo: acceso directo, invitacion pendiente o membresia activa
- los serializers de lectura exponen permisos efectivos y contexto del usuario
  para que el frontend no tenga que inferirlos
- los serializers de escritura limitan cambios peligrosos como reasignar owner o
  mutar el usuario/account de una membresia existente

Que se puede hacer despues:
- extraer un serializer dedicado para onboarding de invitaciones con enlaces o
  deep links
- incluir trazabilidad adicional si Vexxo introduce auditoria por aprobaciones
  o expiracion de invitaciones
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from finance.accounts.models import AccountMembership
from finance.accounts.serializers.account_membership_support import (
    create_account_membership,
    update_account_membership,
    validate_account_membership_payload,
)

User = get_user_model()


class AccountMembershipSerializer(serializers.ModelSerializer):
    """
    Vista detallada de una membresia de cuenta.
    """

    account_name = serializers.CharField(source="account.name", read_only=True)
    account_owner_id = serializers.IntegerField(source="account.owner_id", read_only=True)
    user_display_name = serializers.CharField(source="user.display_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    invited_by_display_name = serializers.CharField(source="invited_by.display_name", read_only=True)
    effective_can_post_transactions = serializers.BooleanField(read_only=True)
    effective_can_manage_members = serializers.BooleanField(read_only=True)
    effective_can_manage_account_settings = serializers.BooleanField(read_only=True)
    invitation_pending = serializers.BooleanField(read_only=True)
    invitation_status = serializers.CharField(read_only=True)
    is_owner = serializers.BooleanField(read_only=True)
    is_admin_or_higher = serializers.BooleanField(read_only=True)
    current_invitation_id = serializers.SerializerMethodField(read_only=True)
    invitation_expires_at = serializers.SerializerMethodField(read_only=True)
    invitation_opened_at = serializers.SerializerMethodField(read_only=True)
    invitation_attempt_number = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AccountMembership
        fields = [
            "id",
            "account",
            "account_name",
            "account_owner_id",
            "user",
            "user_display_name",
            "user_email",
            "role",
            "access_mode",
            "can_post_transactions",
            "can_manage_members",
            "can_manage_account_settings",
            "can_view_analytics",
            "effective_can_post_transactions",
            "effective_can_manage_members",
            "effective_can_manage_account_settings",
            "invited_by",
            "invited_by_display_name",
            "invitation_token",
            "invitation_sent_at",
            "accepted_at",
            "joined_at",
            "revoked_at",
            "is_active",
            "invitation_pending",
            "invitation_status",
            "current_invitation_id",
            "invitation_expires_at",
            "invitation_opened_at",
            "invitation_attempt_number",
            "is_owner",
            "is_admin_or_higher",
            "metadata",
        ]
        read_only_fields = fields

    def get_current_invitation_id(self, obj):
        invitation = obj.current_invitation or obj.latest_invitation
        return invitation.id if invitation else None

    def get_invitation_expires_at(self, obj):
        invitation = obj.current_invitation or obj.latest_invitation
        return invitation.expires_at if invitation else None

    def get_invitation_opened_at(self, obj):
        invitation = obj.current_invitation or obj.latest_invitation
        return invitation.opened_at if invitation else None

    def get_invitation_attempt_number(self, obj):
        invitation = obj.current_invitation or obj.latest_invitation
        return invitation.attempt_number if invitation else None


class AccountMembershipWriteSerializer(serializers.ModelSerializer):
    """
    Alta o edicion operativa de una membresia.
    """

    send_invitation = serializers.BooleanField(write_only=True, required=False, default=True)
    invitation_ttl_days = serializers.IntegerField(write_only=True, required=False, min_value=1, max_value=90, default=14)
    invitation_channel = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=32, default="direct_link")
    invitation_metadata = serializers.JSONField(write_only=True, required=False, default=dict)

    class Meta:
        model = AccountMembership
        fields = [
            "account",
            "user",
            "role",
            "access_mode",
            "can_post_transactions",
            "can_manage_members",
            "can_manage_account_settings",
            "can_view_analytics",
            "is_active",
            "metadata",
            "send_invitation",
            "invitation_ttl_days",
            "invitation_channel",
            "invitation_metadata",
        ]

    def validate(self, attrs):
        return validate_account_membership_payload(attrs=attrs, instance=getattr(self, "instance", None))

    def create(self, validated_data):
        request = self.context.get("request")
        return create_account_membership(validated_data=validated_data, request_user=getattr(request, "user", None))

    def update(self, instance, validated_data):
        return update_account_membership(instance=instance, validated_data=validated_data)


class AccountMembershipAcceptSerializer(serializers.Serializer):
    """
    Aceptacion de invitacion o activacion controlada de membresia.
    """

    invitation_token = serializers.UUIDField(required=True)
    accepted_at = serializers.DateTimeField(required=False)
    joined_at = serializers.DateTimeField(required=False)


class AccountMembershipRevokeSerializer(serializers.Serializer):
    """
    Revocacion o salida voluntaria de una membresia.
    """

    revoked_at = serializers.DateTimeField(required=False)


class AccountMembershipRotateInvitationSerializer(serializers.Serializer):
    """
    Reemision de token de invitacion.
    """

    sent_at = serializers.DateTimeField(required=False)
    ttl_days = serializers.IntegerField(required=False, min_value=1, max_value=90, default=14)
    channel = serializers.CharField(required=False, allow_blank=True, max_length=32, default="direct_link")
