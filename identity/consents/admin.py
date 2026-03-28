from django.contrib import admin

from identity.consents.models import UserConsent


@admin.register(UserConsent)
class UserConsentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "consent_type", "provider", "status", "granted_at", "expires_at")
    search_fields = ("provider", "external_consent_id", "scope_code", "user__email", "user__username")
    list_filter = ("consent_type", "status", "provider")
