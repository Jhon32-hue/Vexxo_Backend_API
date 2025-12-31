from django.urls import path, include
from rest_framework.routers import DefaultRouter
from alerts.views.alert_views import AlertaViewSet

router = DefaultRouter()
router.register(r'alertas', AlertaViewSet, basename='alerta')

urlpatterns = [
    path('', include(router.urls)),
]

