from rest_framework import serializers

from identity.eventing.models import IdentityDomainEventOutbox


class IdentityDomainEventOutboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdentityDomainEventOutbox
        fields = [
            "id",
            "aggregate_type",
            "aggregate_id",
            "event_type",
            "idempotency_key",
            "priority",
            "correlation_id",
            "causation_id",
            "payload",
            "metadata",
            "status",
            "occurred_at",
            "published_at",
            "retry_count",
            "last_error",
            "locked_at",
            "locked_by",
        ]
        read_only_fields = fields


class IdentityOutboxActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
