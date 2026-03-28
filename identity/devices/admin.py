from django.contrib import admin

from identity.devices.models import UserDevice


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "fingerprint", "device_type", "trust_level", "is_active", "last_seen_at")
    search_fields = ("fingerprint", "external_device_id", "user__email", "user__username")
    list_filter = ("device_type", "trust_level", "is_active")
