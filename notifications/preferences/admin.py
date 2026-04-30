from django.contrib import admin

from notifications.preferences.models import NotificationPreference


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "owner",
        "in_app_enabled",
        "push_enabled",
        "email_notifications_enabled",
        "email_marketing_enabled",
        "newsletter_subscribed",
        "welcome_email_sent_at",
    )
    search_fields = ("owner__email", "owner__username")
