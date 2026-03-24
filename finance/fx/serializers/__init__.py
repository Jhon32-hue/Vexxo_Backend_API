"""
Serializers de FX para exponer snapshots de tasas de cambio.

Descripcion general:
- serializa snapshots FX completos para CRUD y exposicion administrativa

Analisis detallado:
- hoy el serializer es plano y expone todos los campos del snapshot para
  facilitar operacion, inspeccion e ingestiones manuales
- conserva el nombre `TasaFXSerializer` para no romper el contrato actual del
  API, aunque el modelo canonico sea `ExchangeRate`
- si luego conectas APIs externas, aqui convendria endurecer que campos son
  editables manualmente y cuales solo vienen de procesos de integracion
"""

from rest_framework import serializers
from finance.fx.models import ExchangeRate


class TasaFXSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = "__all__"
