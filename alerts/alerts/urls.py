from django.urls import path, include
from rest_framework.routers import DefaultRouter
from alerts.alerts.views.alert_views import AlertaViewSet, AlertAiWorkerView

router = DefaultRouter()
router.register(r'alertas', AlertaViewSet, basename='alerta')

urlpatterns = [
    path('internal/ai-worker/', AlertAiWorkerView.as_view(), name='alerts-ai-worker'),
    path('', include(router.urls)),
]
