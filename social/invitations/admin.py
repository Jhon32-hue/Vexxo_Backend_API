from django.contrib import admin

from social.invitations.models import TeamInvitation


@admin.register(TeamInvitation)
class TeamInvitationAdmin(admin.ModelAdmin):
    list_display = ("public_id", "team", "email", "role", "status", "expires_at", "created_at")
    list_filter = ("status", "role")
    search_fields = ("email", "team__name", "invited_by__email")
    readonly_fields = ("public_id", "token", "created_at", "updated_at")
