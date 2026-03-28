from django.contrib import admin

from identity.permissions.models import UserPermissionGrant


@admin.register(UserPermissionGrant)
class UserPermissionGrantAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "permission_code", "scope_type", "status", "source", "expires_at")
    search_fields = ("permission_code", "scope_id", "user__email", "user__username")
    list_filter = ("status", "source", "scope_type")
