"""
Serializer de vinculacion externa de cuentas.

Descripcion general:
- valida el contrato de enlace entre una cuenta local y un proveedor externo

Analisis detallado:
- concentra el payload de integracion para no mezclarlo con el serializer de
  escritura general del agregado
"""

from rest_framework import serializers


class AccountExternalLinkSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64)
    external_id = serializers.CharField(max_length=255)
    external_type = serializers.CharField(required=False, allow_blank=True, max_length=64)
    external_mask = serializers.CharField(required=False, allow_blank=True, max_length=16)
    provider_metadata = serializers.JSONField(required=False)
    next_sync_at = serializers.DateTimeField(required=False)
