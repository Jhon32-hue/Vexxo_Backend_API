# alerts/serializers/alert_serializers.py
from rest_framework import serializers

from alerts.alerts.models.alerts import Alert


class AlertaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = [
            "id",
            "owner",
            "type",
            "category",
            "severity",
            "status",
            "title",
            "message",
            "payload",
            "source",
            "correlation_id",
            "risk_score",
            "ai_summary",
            "ai_tags",
            "is_active",
            "read_at",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        # La mayoría las controlan servicios / backend,
        # el cliente en principio sólo cambia estado (leer, resolver, etc.)
        read_only_fields = [
            "owner",
            "type",
            "category",
            "severity",
            "title",
            "message",
            "payload",
            "source",
            "correlation_id",
            "risk_score",
            "ai_summary",
            "ai_tags",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "status": {"required": False},
            "is_active": {"required": False},
            "read_at": {"required": False},
            "resolved_at": {"required": False},
        }                                       
