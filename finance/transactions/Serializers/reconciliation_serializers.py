from __future__ import annotations

from rest_framework import serializers

from finance.transactions.Models import TransactionReconciliationIssue


class TransactionReconciliationIssueResolveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=TransactionReconciliationIssue.ResolutionAction.choices)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    payload = serializers.JSONField(required=False)


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
