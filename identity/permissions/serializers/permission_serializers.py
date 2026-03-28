from rest_framework import serializers

from identity.permissions.models import (
    PermissionGrantKind,
    PermissionSource,
    PermissionStatus,
    UserPermissionGrant,
)


class UserPermissionGrantSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPermissionGrant
        fields = [
            "id",
            "user",
            "permission_code",
            "scope_type",
            "scope_id",
            "status",
            "source",
            "grant_kind",
            "granted_by",
            "granted_at",
            "revoked_at",
            "expires_at",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["granted_at", "revoked_at", "created_at", "updated_at"]

    def validate_status(self, value):
        if value not in PermissionStatus.values:
            raise serializers.ValidationError("Estado de permiso invalido.")
        return value

    def validate_source(self, value):
        if value not in PermissionSource.values:
            raise serializers.ValidationError("Fuente de permiso invalida.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        status_value = attrs.get("status")
        grant_kind = attrs.get("grant_kind")

        if self.instance is not None:
            status_value = status_value or self.instance.status
            grant_kind = grant_kind or self.instance.grant_kind

        if status_value == PermissionStatus.DENIED and grant_kind == PermissionGrantKind.ENTITLEMENT:
            raise serializers.ValidationError(
                {
                    "grant_kind": (
                        "Un entitlement no debe usarse para una denegacion explicita. "
                        "Usa grant_kind=override o manual."
                    )
                }
            )
        return attrs


class UserPermissionRevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=128, required=False, allow_blank=True)
