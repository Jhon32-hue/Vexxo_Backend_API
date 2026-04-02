"""
Serializers de comandos de sincronizacion externa.

Descripcion general:
- valida los payloads de schedule, running, success y error del sync de una
  cuenta vinculada

Analisis detallado:
- mantenerlos aislados hace explicito que el flujo de sync es un subdominio
  operativo distinto del CRUD normal de la cuenta
"""

from rest_framework import serializers


class AccountSyncScheduleSerializer(serializers.Serializer):
    delay_minutes = serializers.IntegerField(required=False, min_value=1, max_value=10080, default=30)
    run_at = serializers.DateTimeField(required=False)
    sync_run_id = serializers.CharField(required=False, allow_blank=False, max_length=64)


class AccountSyncRunningSerializer(serializers.Serializer):
    sync_run_id = serializers.CharField(required=False, allow_blank=False, max_length=64)
    sync_cursor = serializers.CharField(required=False, allow_blank=True, max_length=255)
    next_sync_at = serializers.DateTimeField(required=False)


class AccountSyncSuccessSerializer(serializers.Serializer):
    sync_run_id = serializers.CharField(required=False, allow_blank=False, max_length=64)
    duration_ms = serializers.IntegerField(required=False, min_value=0, default=0)
    sync_cursor = serializers.CharField(required=False, allow_blank=True, max_length=255)
    next_sync_at = serializers.DateTimeField(required=False)
    provider_metadata = serializers.JSONField(required=False)


class AccountSyncErrorSerializer(serializers.Serializer):
    sync_run_id = serializers.CharField(required=False, allow_blank=False, max_length=64)
    message = serializers.CharField(max_length=255)
    retry_in_minutes = serializers.IntegerField(required=False, min_value=1, max_value=10080)
    next_sync_at = serializers.DateTimeField(required=False)
