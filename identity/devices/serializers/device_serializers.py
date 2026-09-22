from rest_framework import serializers

import base64

from identity.devices.models import DevicePlatformAttestationChallenge, DeviceTrustLevel, DeviceType, UserDevice


class UserDeviceSerializer(serializers.ModelSerializer):
    platform_verified_active = serializers.BooleanField(read_only=True)
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
            "signing_algorithm",
            "key_verified_at",
            "attestation_provider",
            "attestation_status",
            "platform_verified_at",
            "platform_verification_expires_at",
            "platform_verified_active",
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
            "trust_level",
            "signing_algorithm",
            "key_verified_at",
            "attestation_provider",
            "attestation_status",
            "platform_verified_at",
            "platform_verification_expires_at",
            "platform_verified_active",
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
            "signing_algorithm",
            "signing_public_key",
        ]

    def validate_fingerprint(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Fingerprint requerido.")
        return value

    def validate(self, attrs):
        algorithm = str(attrs.get("signing_algorithm") or "").strip().lower()
        public_key = str(attrs.get("signing_public_key") or "").strip()
        if bool(algorithm) != bool(public_key):
            raise serializers.ValidationError("La clave publica y su algoritmo deben enviarse juntos.")
        if algorithm and algorithm != "ed25519":
            raise serializers.ValidationError({"signing_algorithm": "Solo se admite Ed25519."})
        if public_key:
            try:
                decoded = base64.b64decode(public_key, validate=True)
            except ValueError as exc:
                raise serializers.ValidationError({"signing_public_key": "Clave publica invalida."}) from exc
            if len(decoded) != 32:
                raise serializers.ValidationError({"signing_public_key": "Una clave Ed25519 debe tener 32 bytes."})
        attrs["signing_algorithm"] = algorithm
        attrs["signing_public_key"] = public_key
        return attrs


class DeviceSignatureVerifySerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    nonce = serializers.CharField(max_length=128)
    signature = serializers.CharField(max_length=256)
    purpose = serializers.ChoiceField(choices=["register_key", "step_up"], default="register_key")


class DevicePlatformAttestationChallengeSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=DevicePlatformAttestationChallenge.Provider.choices)


class DevicePlatformAttestationVerifySerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=DevicePlatformAttestationChallenge.Provider.choices)
    nonce = serializers.CharField(max_length=128)
    token = serializers.CharField(required=False, allow_blank=True, max_length=65536)
    key_id = serializers.CharField(required=False, allow_blank=True, max_length=512)
    attestation_object = serializers.CharField(required=False, allow_blank=True, max_length=131072)

    def validate(self, attrs):
        if attrs["provider"] == DevicePlatformAttestationChallenge.Provider.PLAY_INTEGRITY:
            if not attrs.get("token"):
                raise serializers.ValidationError({"token": "Token de Play Integrity requerido."})
        elif not attrs.get("key_id") or not attrs.get("attestation_object"):
            raise serializers.ValidationError("key_id y attestation_object son requeridos para App Attest.")
        return attrs
