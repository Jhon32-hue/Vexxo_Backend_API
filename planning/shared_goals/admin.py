from django.contrib import admin

from planning.shared_goals.models import SharedGoal


@admin.register(SharedGoal)
class SharedGoalAdmin(admin.ModelAdmin):
    list_display = ("goal", "team", "contribution_policy", "is_active", "created_at")
    list_filter = ("contribution_policy", "is_active")
    search_fields = ("goal__name", "team__name", "created_by__email")
    readonly_fields = ("created_at", "updated_at", "revoked_at", "revocation_reason")
