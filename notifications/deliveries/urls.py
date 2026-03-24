"""
Rutas del inbox persistente de notificaciones.

Descripcion general:
- publica la API REST de `notifications.deliveries`
- mantiene separado el contrato HTTP del listener/evento que origino la entrega
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from notifications.deliveries.views import NotificationDeliveryViewSet

router = DefaultRouter()
router.register(r"entregas-notificacion", NotificationDeliveryViewSet, basename="notification-deliveries")

urlpatterns = [
    path("", include(router.urls)),
]
