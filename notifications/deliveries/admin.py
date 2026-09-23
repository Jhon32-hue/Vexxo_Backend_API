from django.contrib import admin

from notifications.deliveries.models import NotificationDelivery


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "notification_key", "category", "priority", "channel", "status", "created_at")
    list_filter = ("category", "priority", "channel", "status", "event_type")
    search_fields = ("notification_key", "title", "message", "event_type", "owner__email")
    readonly_fields = ("created_at", "updated_at", "delivered_at", "read_at")
