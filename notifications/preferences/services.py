from __future__ import annotations

from notifications.preferences.models import NotificationPreference


def get_or_create_notification_preferences(user) -> NotificationPreference:
    defaults = {
        "email_marketing_enabled": bool(getattr(user, "marketing_opt_in", False)),
        "newsletter_subscribed": bool(getattr(user, "marketing_opt_in", False)),
    }
    preferences, created = NotificationPreference.objects.get_or_create(
        owner=user,
        defaults=defaults,
    )
    if created:
        return preferences

    marketing_opt_in = bool(getattr(user, "marketing_opt_in", False))
    dirty_fields: list[str] = []
    if marketing_opt_in and not preferences.email_marketing_enabled:
        preferences.email_marketing_enabled = True
        dirty_fields.append("email_marketing_enabled")
    if marketing_opt_in and not preferences.newsletter_subscribed:
        preferences.newsletter_subscribed = True
        dirty_fields.append("newsletter_subscribed")
    if dirty_fields:
        dirty_fields.append("updated_at")
        preferences.save(update_fields=dirty_fields)
    return preferences
