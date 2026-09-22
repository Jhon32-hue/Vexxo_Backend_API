from django.contrib import admin

from security.models import KeyRotationJob, SecurityAuditEvent, SecurityThrottleBucket


@admin.register(SecurityAuditEvent)
class SecurityAuditEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "severity", "source", "request_id", "created_at")
    list_filter = ("severity", "event_type")
    search_fields = ("request_id", "target_id")
    readonly_fields = [field.name for field in SecurityAuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SecurityThrottleBucket)
class SecurityThrottleBucketAdmin(admin.ModelAdmin):
    list_display = ("scope", "request_count", "blocked_until", "updated_at")
    readonly_fields = ("subject_hash",)


@admin.register(KeyRotationJob)
class KeyRotationJobAdmin(admin.ModelAdmin):
    list_display = ("from_version", "to_version", "status", "processed_count", "failed_count", "created_at")
    readonly_fields = [field.name for field in KeyRotationJob._meta.fields]
