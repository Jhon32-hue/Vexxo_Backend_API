from rest_framework import serializers

from identity.consents.models import ConsentStatus, ConsentType, UserConsent


class UserConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserConsent
        fields = [
            "id",
            "user",
            "consent_type",
            "provider",
            "external_consent_id",
            "scope_code",
            "status",
            "purpose",
            "legal_basis",
            "terms_version",
            "privacy_version",
            "granted_at",
            "revoked_at",
            "expires_at",
            "granted_via",
            "data_categories",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["user", "granted_at", "revoked_at", "created_at", "updated_at"]

    def validate_consent_type(self, value):
        if value not in ConsentType.values:
            raise serializers.ValidationError("Tipo de consentimiento invalido.")
        return value

    def validate_status(self, value):
        if value not in ConsentStatus.values:
            raise serializers.ValidationError("Estado de consentimiento invalido.")
        return value


class UserConsentGrantSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserConsent
        fields = [
            "consent_type",
            "provider",
            "external_consent_id",
            "scope_code",
            "purpose",
            "legal_basis",
            "terms_version",
            "privacy_version",
            "expires_at",
            "granted_via",
            "data_categories",
            "metadata",
        ]


class UserConsentRevokeSerializer(serializers.Serializer):
    revoke_reason = serializers.CharField(max_length=128, required=False, allow_blank=True)
