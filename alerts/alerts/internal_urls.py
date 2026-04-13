from django.urls import path

from alerts.alerts.views.alert_views import AlertAiWorkerView


urlpatterns = [
    path("ai-worker/", AlertAiWorkerView.as_view(), name="alerts-internal-ai-worker"),
]
