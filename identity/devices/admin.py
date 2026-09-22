from django.contrib import admin

from identity.devices.models import DevicePlatformAttestationChallenge, DeviceSignatureChallenge, UserDevice


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "fingerprint", "device_type", "trust_level", "is_active", "last_seen_at")
    search_fields = ("fingerprint", "external_device_id", "user__email", "user__username")
    list_filter = ("device_type", "trust_level", "is_active")


@admin.register(DeviceSignatureChallenge)
class DeviceSignatureChallengeAdmin(admin.ModelAdmin):
    list_display = ("public_id", "device", "purpose", "expires_at", "consumed_at", "failed_attempts")
    list_filter = ("purpose", "consumed_at")
    readonly_fields = ("nonce_hash",)


@admin.register(DevicePlatformAttestationChallenge)
class DevicePlatformAttestationChallengeAdmin(admin.ModelAdmin):
    list_display = ("public_id", "device", "provider", "expires_at", "consumed_at", "failed_attempts")
    list_filter = ("provider", "consumed_at")
    readonly_fields = ("nonce_hash", "request_hash")
