from rest_framework import serializers

from identity.devices.models import DeviceTrustLevel, DeviceType, UserDevice


class UserDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDevice
        fields = [
            "id",
            "user",
            "external_device_id",
            "fingerprint",
            "name",
            "device_type",
            "platform",
            "os_version",
            "app_version",
            "user_agent",
            "push_token",
            "ip_address",
            "locale",
            "timezone_name",
            "trust_level",
            "is_active",
            "is_primary",
            "first_seen_at",
            "last_seen_at",
            "trusted_at",
            "revoked_at",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "user",
            "first_seen_at",
            "last_seen_at",
            "trusted_at",
            "revoked_at",
            "created_at",
            "updated_at",
        ]

    def validate_device_type(self, value):
        if value not in DeviceType.values:
            raise serializers.ValidationError("Tipo de dispositivo no soportado.")
        return value

    def validate_trust_level(self, value):
        if value not in DeviceTrustLevel.values:
            raise serializers.ValidationError("Trust level invalido.")
        return value


class UserDeviceTrustSerializer(serializers.Serializer):
    trust_level = serializers.ChoiceField(choices=DeviceTrustLevel.choices, default=DeviceTrustLevel.TRUSTED)


class UserDeviceRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDevice
        fields = [
            "fingerprint",
            "external_device_id",
            "name",
            "device_type",
            "platform",
            "os_version",
            "app_version",
            "push_token",
            "locale",
            "timezone_name",
            "metadata",
        ]

    def validate_fingerprint(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Fingerprint requerido.")
        return value
