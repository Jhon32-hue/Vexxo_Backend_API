from django.contrib import admin

from identity.eventing.models import (
    IdentityDomainEventOutbox,
    UserProductUsageProjection,
    UserProductUsageProjectionEvent,
)


@admin.register(IdentityDomainEventOutbox)
class IdentityDomainEventOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "aggregate_type", "aggregate_id", "event_type", "status", "occurred_at", "published_at")
    list_filter = ("status", "aggregate_type", "event_type")
    search_fields = ("aggregate_id", "event_type", "idempotency_key")
    readonly_fields = ("occurred_at", "published_at", "retry_count", "last_error")


@admin.register(UserProductUsageProjection)
class UserProductUsageProjectionAdmin(admin.ModelAdmin):
    list_display = (
        "owner",
        "manual_accounts_count",
        "connected_accounts_count",
        "rules_count",
        "ai_used_month",
        "payments_count_month",
        "shared_memberships_count",
        "refreshed_at",
    )
    search_fields = ("owner__username", "owner__email")
    readonly_fields = ("refreshed_at",)


@admin.register(UserProductUsageProjectionEvent)
class UserProductUsageProjectionEventAdmin(admin.ModelAdmin):
    list_display = ("owner", "event_type", "event_id", "correlation_id", "processed_at")
    list_filter = ("event_type",)
    search_fields = ("owner__username", "owner__email", "event_id", "correlation_id", "fingerprint")
    readonly_fields = ("processed_at",)
