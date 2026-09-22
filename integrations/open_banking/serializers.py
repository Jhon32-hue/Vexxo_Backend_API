from rest_framework import serializers

from integrations.open_banking.models import (
    OpenBankingAccountLink,
    OpenBankingConnection,
    OpenBankingInstitution,
    OpenBankingTimelineEvent,
)
from integrations.open_banking.provider_catalog import get_provider
from integrations.open_banking.services import start_open_banking_connection


class OpenBankingInstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpenBankingInstitution
        fields = [
            "public_id", "code", "name", "country", "logo_path", "logo_sha256",
            "logo_license", "logo_provenance", "logo_version", "updated_at",
        ]
        read_only_fields = fields


class OpenBankingTimelineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpenBankingTimelineEvent
        fields = ["id", "event_type", "source", "status", "provider_event_id", "occurred_at", "safe_metadata"]
        read_only_fields = fields


class OpenBankingAccountLinkSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    account_currency = serializers.CharField(source="account.currency", read_only=True)

    class Meta:
        model = OpenBankingAccountLink
        fields = [
            "id",
            "account",
            "account_name",
            "account_currency",
            "external_mask",
            "external_type",
            "is_active",
            "updated_at",
        ]
        read_only_fields = fields


class OpenBankingConnectionSerializer(serializers.ModelSerializer):
    authorization_url = serializers.SerializerMethodField()
    widget_access_token = serializers.SerializerMethodField()
    account_links = OpenBankingAccountLinkSerializer(many=True, read_only=True)
    provider_name = serializers.SerializerMethodField()
    provider_configured = serializers.SerializerMethodField()
    consent_status = serializers.CharField(source="consent.status", read_only=True)
    consent_purpose = serializers.CharField(source="consent.purpose", read_only=True)
    consent_granted_at = serializers.DateTimeField(source="consent.granted_at", read_only=True)
    consent_expires_at = serializers.DateTimeField(source="consent.expires_at", read_only=True)
    consent_revoked_at = serializers.DateTimeField(source="consent.revoked_at", read_only=True)
    data_categories = serializers.ListField(source="consent.data_categories", read_only=True)
    revocation_effects = serializers.SerializerMethodField()
    institution_code = serializers.SlugRelatedField(
        source="institution",
        slug_field="code",
        queryset=OpenBankingInstitution.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        write_only=True,
    )
    institution_details = OpenBankingInstitutionSerializer(source="institution", read_only=True)

    class Meta:
        model = OpenBankingConnection
        fields = [
            "public_id",
            "provider",
            "provider_name",
            "provider_configured",
            "authorization_url",
            "widget_access_token",
            "institution_name",
            "institution_code",
            "institution_details",
            "country",
            "status",
            "scopes",
            "consent_status",
            "consent_purpose",
            "consent_granted_at",
            "consent_expires_at",
            "consent_revoked_at",
            "data_categories",
            "revocation_effects",
            "last_synced_at",
            "next_sync_at",
            "credential_expires_at",
            "reauthorization_required_at",
            "error_code",
            "error_message",
            "account_links",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "provider_name",
            "provider_configured",
            "authorization_url",
            "widget_access_token",
            "consent_status",
            "consent_purpose",
            "consent_granted_at",
            "consent_expires_at",
            "consent_revoked_at",
            "data_categories",
            "revocation_effects",
            "status",
            "last_synced_at",
            "next_sync_at",
            "credential_expires_at",
            "reauthorization_required_at",
            "error_code",
            "error_message",
            "account_links",
            "created_at",
            "updated_at",
        ]

    def get_provider_name(self, obj) -> str:
        provider = get_provider(obj.provider)
        return provider.name if provider else obj.provider

    def get_provider_configured(self, obj) -> bool:
        provider = get_provider(obj.provider)
        return bool(provider and provider.configured)

    def get_authorization_url(self, obj) -> str:
        return getattr(obj, "_authorization_url", "")

    def get_widget_access_token(self, obj) -> str:
        return getattr(obj, "_widget_access_token", "")

    def get_revocation_effects(self, obj) -> dict:
        return {
            "future_collection_stops": True,
            "scheduled_sync_stops": True,
            "imported_ledger_is_retained": True,
            "data_deletion_is_separate": True,
        }

    def create(self, validated_data):
        request = self.context["request"]
        return start_open_banking_connection(
            owner=request.user,
            provider_code=validated_data["provider"],
            institution_name=validated_data.get("institution_name", ""),
            country=validated_data.get("country", ""),
            scopes=validated_data.get("scopes"),
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            institution=validated_data.get("institution"),
        )


class ImportOpenBankingAccountSerializer(serializers.Serializer):
    external_account_id = serializers.CharField(max_length=160)


class OpenBankingWebhookSerializer(serializers.Serializer):
    vexxo_connection_id = serializers.UUIDField(required=False)
    event_id = serializers.CharField(required=False, max_length=160)
    id = serializers.CharField(required=False, max_length=160)
    event_type = serializers.CharField(required=False, max_length=96)
    type = serializers.CharField(required=False, max_length=96)
    connection_id = serializers.CharField(required=False, allow_blank=True, max_length=160)
    link_id = serializers.CharField(required=False, allow_blank=True, max_length=160)
    status = serializers.CharField(required=False, allow_blank=True, max_length=64)
    reason_code = serializers.CharField(required=False, allow_blank=True, max_length=64)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    sequence = serializers.IntegerField(required=False, allow_null=True, min_value=0)

    def validate(self, attrs):
        if not attrs.get("event_id") and not attrs.get("id"):
            raise serializers.ValidationError({"event_id": "event_id o id es requerido."})
        if not attrs.get("event_type") and not attrs.get("type"):
            raise serializers.ValidationError({"event_type": "event_type o type es requerido."})
        return attrs
