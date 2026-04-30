from __future__ import annotations

from rest_framework import serializers

from notifications.preferences.models import NotificationPreference


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "in_app_enabled",
            "push_enabled",
            "email_notifications_enabled",
            "email_marketing_enabled",
            "newsletter_subscribed",
            "welcome_email_sent_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["welcome_email_sent_at", "created_at", "updated_at"]
