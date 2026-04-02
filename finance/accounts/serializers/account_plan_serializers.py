"""
Serializer de snapshot operativo de plan para `accounts`.

Descripcion general:
- expone limites y uso actual del owner dentro del bounded context de cuentas

Analisis detallado:
- este payload no persiste estado; representa una lectura derivada de guards y
  uso del owner para informar decisiones de producto y validacion
"""

from rest_framework import serializers


class AccountPlanUsageSerializer(serializers.Serializer):
    plan = serializers.CharField()
    limits = serializers.JSONField()
    usage = serializers.JSONField()
