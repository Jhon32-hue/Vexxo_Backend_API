from rest_framework import serializers

from identity.sessions.models import SessionStatus, SessionType, UserSession


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = [
            "id",
            "user",
            "device",
            "session_key",
            "family_id",
            "refresh_jti",
            "previous_refresh_jti",
            "access_jti",
            "session_type",
            "status",
            "risk_level",
            "requires_step_up",
            "provider",
            "ip_address",
            "user_agent",
            "authenticated_at",
            "last_seen_at",
            "last_refreshed_at",
            "refresh_rotated_at",
            "expires_at",
            "revoked_at",
            "revocation_reason",
            "correlation_id",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "user",
            "authenticated_at",
            "last_seen_at",
            "revoked_at",
            "created_at",
            "updated_at",
        ]

    def validate_session_type(self, value):
        if value not in SessionType.values:
            raise serializers.ValidationError("Tipo de sesion invalido.")
        return value

    def validate_status(self, value):
        if value not in SessionStatus.values:
            raise serializers.ValidationError("Estado de sesion invalido.")
        return value


class UserSessionRegisterSerializer(serializers.Serializer):
    session_key = serializers.CharField(max_length=128, required=False, allow_blank=True)
    refresh_jti = serializers.CharField(max_length=128, required=False, allow_blank=True)
    access_jti = serializers.CharField(max_length=128, required=False, allow_blank=True)
    session_type = serializers.ChoiceField(choices=SessionType.choices, default=SessionType.PASSWORD)
    provider = serializers.CharField(max_length=32, required=False, allow_blank=True)
    device_id = serializers.IntegerField(required=False, allow_null=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    correlation_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    family_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)


class UserSessionRevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=64, required=False, allow_blank=True)
