from __future__ import annotations

from rest_framework import serializers

from finance.transactions.Models import TransactionReconciliationIssue


def _validate_reconciliation_json_object(*, field_name: str, value):
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError({field_name: "Debe ser un objeto JSON."})
    invalid_keys = [key for key in value.keys() if not isinstance(key, str) or not key.strip()]
    if invalid_keys:
        raise serializers.ValidationError({field_name: "Todas las claves deben ser strings no vacios."})
    return value


class TransactionReconciliationIssueResolveSerializer(serializers.Serializer):
    """Superficie internal-trusted para resolucion operativa de reconciliacion."""
    action = serializers.ChoiceField(choices=TransactionReconciliationIssue.ResolutionAction.choices)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    payload = serializers.JSONField(required=False)

    def validate_payload(self, value):
        return _validate_reconciliation_json_object(field_name="payload", value=value)


class TransactionReconciliationIssueResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionReconciliationIssue
        fields = [
            "id",
            "transaction",
            "source_link",
            "issue_type",
            "status",
            "summary",
            "details",
            "resolution_action",
            "resolution_notes",
            "resolution_payload",
            "resolved_by",
            "resolution_transaction",
            "created_at",
            "resolved_at",
            "updated_at",
        ]
