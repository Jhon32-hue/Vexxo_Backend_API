from django.contrib import admin

from integrations.open_banking.models import (
    OpenBankingAccountLink,
    OpenBankingConnection,
    OpenBankingExternalPayload,
    OpenBankingInstitution,
    OpenBankingProviderInstitution,
    OpenBankingReconciliationIssue,
    OpenBankingSyncRun,
    OpenBankingTimelineEvent,
    OpenBankingWebhookReceipt,
)


@admin.register(OpenBankingConnection)
class OpenBankingConnectionAdmin(admin.ModelAdmin):
    list_display = ("public_id", "owner", "provider", "institution_name", "status", "updated_at")
    list_filter = ("provider", "status", "country")
    search_fields = ("public_id", "owner__email", "institution_name")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(OpenBankingAccountLink)
class OpenBankingAccountLinkAdmin(admin.ModelAdmin):
    list_display = ("connection", "account", "external_mask", "is_active", "updated_at")
    list_filter = ("is_active", "connection__provider")
    search_fields = ("account__name", "account__owner__email")


@admin.register(OpenBankingWebhookReceipt)
class OpenBankingWebhookReceiptAdmin(admin.ModelAdmin):
    list_display = ("provider", "provider_event_id", "event_type", "status", "signature_verified", "received_at")
    list_filter = ("provider", "status", "signature_verified")
    search_fields = ("provider_event_id", "connection_reference", "payload_sha256")
    readonly_fields = [field.name for field in OpenBankingWebhookReceipt._meta.fields]


for model in (
    OpenBankingInstitution,
    OpenBankingProviderInstitution,
    OpenBankingExternalPayload,
    OpenBankingSyncRun,
    OpenBankingTimelineEvent,
    OpenBankingReconciliationIssue,
):
    admin.site.register(model)
