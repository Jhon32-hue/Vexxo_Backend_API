from django.contrib import admin

from identity.sessions.models import UserSession


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "session_type", "status", "authenticated_at", "last_seen_at")
    search_fields = ("session_key", "refresh_jti", "user__email", "user__username")
    list_filter = ("session_type", "status", "provider")
