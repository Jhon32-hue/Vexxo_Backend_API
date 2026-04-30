"""
API de preferencias de comunicacion del usuario.
"""

from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from identity.users.services.communication_service import update_marketing_preferences
from notifications.preferences.serializers import NotificationPreferenceSerializer
from notifications.preferences.services import get_or_create_notification_preferences


class NotificationPreferenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        preferences = get_or_create_notification_preferences(request.user)
        return Response(NotificationPreferenceSerializer(preferences).data, status=status.HTTP_200_OK)

    def put(self, request):
        preferences = get_or_create_notification_preferences(request.user)
        serializer = NotificationPreferenceSerializer(preferences, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        update_marketing_preferences(
            user=request.user,
            newsletter_subscribed=serializer.instance.newsletter_subscribed,
            email_marketing_enabled=serializer.instance.email_marketing_enabled,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        preferences = get_or_create_notification_preferences(request.user)
        serializer = NotificationPreferenceSerializer(preferences, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        update_marketing_preferences(
            user=request.user,
            newsletter_subscribed=serializer.instance.newsletter_subscribed,
            email_marketing_enabled=serializer.instance.email_marketing_enabled,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
