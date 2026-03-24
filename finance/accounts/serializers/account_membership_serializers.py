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
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from finance.accounts.domain.enums import AccountMembershipRole
from finance.accounts.models import Account, AccountMembership

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
    is_owner = serializers.BooleanField(read_only=True)
    is_admin_or_higher = serializers.BooleanField(read_only=True)

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
            "is_owner",
            "is_admin_or_higher",
            "metadata",
        ]
        read_only_fields = fields


class AccountMembershipWriteSerializer(serializers.ModelSerializer):
    """
    Alta o edicion operativa de una membresia.
    """

    send_invitation = serializers.BooleanField(write_only=True, required=False, default=True)

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
        ]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        account = attrs.get("account", getattr(instance, "account", None))
        user = attrs.get("user", getattr(instance, "user", None))
        role = attrs.get("role", getattr(instance, "role", None))

        if not account:
            raise serializers.ValidationError({"account": _("La cuenta es requerida.")})
        if not user:
            raise serializers.ValidationError({"user": _("El usuario es requerido.")})

        if instance:
            if "account" in attrs and attrs["account"].pk != instance.account_id:
                raise serializers.ValidationError({"account": _("No puedes mover una membresia a otra cuenta.")})
            if "user" in attrs and attrs["user"].pk != instance.user_id:
                raise serializers.ValidationError({"user": _("No puedes cambiar el usuario de una membresia existente.")})

        duplicate_qs = AccountMembership.objects.filter(account=account, user=user)
        if instance:
            duplicate_qs = duplicate_qs.exclude(pk=instance.pk)
        if duplicate_qs.exists():
            raise serializers.ValidationError({"user": _("Ese usuario ya tiene una membresia para esta cuenta.")})

        if user.id == account.owner_id and not instance:
            raise serializers.ValidationError(
                {"user": _("El owner de la cuenta no debe crearse por este flujo; usa ensure_owner_membership().")}
            )

        if role == AccountMembershipRole.OWNER and user.id != account.owner_id:
            raise serializers.ValidationError(
                {"role": _("Solo el owner real de la cuenta puede tener rol owner.")}
            )

        return attrs

    def create(self, validated_data):
        send_invitation = validated_data.pop("send_invitation", True)
        request = self.context.get("request")
        validated_data.setdefault("invited_by", getattr(request, "user", None))

        membership = AccountMembership(**validated_data)
        if not membership.is_active and send_invitation and membership.invitation_sent_at is None:
            membership.invitation_sent_at = timezone.now()
        membership.full_clean()
        membership.save()
        return membership

    def update(self, instance, validated_data):
        validated_data.pop("send_invitation", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.full_clean()
        instance.save()
        return instance


class AccountMembershipAcceptSerializer(serializers.Serializer):
    """
    Aceptacion de invitacion o activacion controlada de membresia.
    """

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
