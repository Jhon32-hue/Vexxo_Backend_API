from django.urls import path

from notifications.preferences.views import NotificationPreferenceView

urlpatterns = [
    path("me/", NotificationPreferenceView.as_view(), name="notification-preferences-me"),
]
