from django.contrib import admin

from identity.eventing.models import IdentityDomainEventOutbox


@admin.register(IdentityDomainEventOutbox)
class IdentityDomainEventOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "aggregate_type", "aggregate_id", "event_type", "status", "occurred_at", "published_at")
    list_filter = ("status", "aggregate_type", "event_type")
    search_fields = ("aggregate_id", "event_type", "idempotency_key")
    readonly_fields = ("occurred_at", "published_at", "retry_count", "last_error")
