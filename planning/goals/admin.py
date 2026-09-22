from django.contrib import admin

from planning.goals.models import Goal, GoalContribution, GoalDomainEventOutbox, GoalMilestone


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "status", "progress", "target_amount", "target_date")
    list_filter = ("status", "active", "target_date")
    search_fields = ("name", "owner__email")
    readonly_fields = ("progress", "status", "active", "completed_at", "created_at", "updated_at")


@admin.register(GoalContribution)
class GoalContributionAdmin(admin.ModelAdmin):
    list_display = ("id", "goal", "owner", "amount", "contributed_on", "source", "reversed_at")
    list_filter = ("source", "contributed_on", "reversed_at")
    search_fields = ("goal__name", "owner__email", "idempotency_key")
    readonly_fields = [field.name for field in GoalContribution._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GoalMilestone)
class GoalMilestoneAdmin(admin.ModelAdmin):
    list_display = ("goal", "name", "target_amount", "achieved_at")
    search_fields = ("goal__name", "owner__email", "name")
    readonly_fields = ("achieved_at", "created_at")

@admin.register(GoalDomainEventOutbox)
class GoalDomainEventOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "aggregate_type", "aggregate_id", "status", "occurred_at")
    list_filter = ("status", "event_type")
    search_fields = ("aggregate_id", "idempotency_key", "correlation_id")
    readonly_fields = [field.name for field in GoalDomainEventOutbox._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
