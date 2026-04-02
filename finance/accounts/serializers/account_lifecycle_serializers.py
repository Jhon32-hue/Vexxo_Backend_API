"""
Serializers pequenos para acciones de lifecycle.

Descripcion general:
- modela inputs minimos para acciones como freeze, archive o recalc manual

Analisis detallado:
- se separan de lectura/escritura completa porque representan comandos
  operativos del agregado, no actualizaciones generales del recurso
"""

from rest_framework import serializers


class AccountReasonActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class AccountRecalcSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
        default="manual_recalc",
    )
