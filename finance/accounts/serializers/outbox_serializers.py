"""
Serializers para observabilidad y control del outbox transaccional.

Descripcion general:
- exponen lectura del `DomainEventOutbox`
- modelan acciones operativas simples sobre eventos pendientes o fallidos

Analisis detallado:
- el outbox es parte critica del bounded context de accounts porque protege la
  publicacion de eventos frente a fallos del bus o de workers
- la API no deberia permitir edicion libre del evento, pero si operaciones
  controladas de soporte como reintentar publicacion o liberar locks
- la vista de detalle necesita mostrar payload, metadata y estado operativo
  real para diagnosticar incidentes

Que se puede hacer despues:
- agregar filtros por correlation_id cuando Vexxo expanda trazabilidad
- incluir una vista resumida de salud del outbox por aggregate_type o event_type
"""

from __future__ import annotations

from rest_framework import serializers

from finance.accounts.models import DomainEventOutbox


class DomainEventOutboxSerializer(serializers.ModelSerializer):
    """
    Vista de lectura del outbox de dominio.
    """

    is_published = serializers.BooleanField(read_only=True)
    is_pending = serializers.BooleanField(read_only=True)
    is_locked = serializers.BooleanField(read_only=True)
    is_processing = serializers.BooleanField(read_only=True)

    class Meta:
        model = DomainEventOutbox
        fields = [
            "id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "idempotency_key",
            "payload",
            "metadata",
            "status",
            "occurred_at",
            "published_at",
            "retry_count",
            "last_error",
            "locked_at",
            "locked_by",
            "is_published",
            "is_pending",
            "is_locked",
            "is_processing",
        ]
        read_only_fields = fields


class OutboxActionSerializer(serializers.Serializer):
    """
    Placeholder para acciones sin payload complejo.
    """

    pass
