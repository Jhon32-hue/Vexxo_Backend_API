"""
Rutas de consulta para senales realtime persistidas.

Descripcion general:
- publica el feed tecnico de `RealtimeSignal`
- permite polling sencillo sin acoplar la UI al event bus interno
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from realtime.consumers.views import RealtimeSignalViewSet

router = DefaultRouter()
router.register(r"senales-realtime", RealtimeSignalViewSet, basename="realtime-signals")

urlpatterns = [
    path("", include(router.urls)),
]
