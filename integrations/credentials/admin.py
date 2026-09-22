from django.contrib import admin

from integrations.credentials.models import IntegrationCredential


@admin.register(IntegrationCredential)
class IntegrationCredentialAdmin(admin.ModelAdmin):
    list_display = ("provider", "credential_type", "owner", "status", "key_version", "expires_at", "updated_at")
    list_filter = ("provider", "credential_type", "status", "key_version")
    search_fields = ("owner__email", "external_reference")
    exclude = ("encrypted_payload",)
    readonly_fields = ("public_id", "key_version", "created_at", "updated_at", "last_rotated_at")
