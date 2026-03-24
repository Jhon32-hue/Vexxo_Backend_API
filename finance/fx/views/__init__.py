"""
Viewsets de FX.

Descripcion general:
- expone CRUD administrativo de snapshots FX

Analisis detallado:
- hoy este viewset sirve para operar o inspeccionar tasas ya persistidas
- ordena por `observed_at`, no por fecha de creacion, porque en FX importa el
  momento real observado de la tasa
- actualmente no implementa la logica de "traer la ultima tasa desde internet";
  esa responsabilidad deberia vivir en un servicio o job de integracion
"""

from rest_framework import viewsets
from finance.fx.models import ExchangeRate
from finance.fx.serializers import TasaFXSerializer


class TasaFXViewSet(viewsets.ModelViewSet):
    queryset = ExchangeRate.objects.all().order_by("-observed_at")
    serializer_class = TasaFXSerializer
