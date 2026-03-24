from django.contrib import admin

from realtime.consumers.models import RealtimeSignal


@admin.register(RealtimeSignal)
class RealtimeSignalAdmin(admin.ModelAdmin):
    list_display = ("id", "owner_id", "channel", "event", "aggregate_type", "aggregate_id", "created_at")
    list_filter = ("channel", "event", "aggregate_type")
    search_fields = ("aggregate_id", "event")
    readonly_fields = ("created_at", "published_at")
