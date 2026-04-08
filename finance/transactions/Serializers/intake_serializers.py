from __future__ import annotations

from rest_framework import serializers

from finance.transactions.Models import TransactionIntakeBatch


class TransactionIntakeRowSerializer(serializers.Serializer):
    account_id = serializers.IntegerField(required=False)
    internal_account_id = serializers.IntegerField(required=False)
    external_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    provider_event_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    provider_status = serializers.CharField(required=False, allow_blank=True, max_length=64)
    type = serializers.ChoiceField(choices=["expense", "income", "transfer"], required=False, default="expense")
    status = serializers.ChoiceField(
        choices=["pending", "posted", "reconciled", "canceled", "failed"],
        required=False,
        default="posted",
    )
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    date = serializers.DateField()
    currency = serializers.CharField(required=False, allow_blank=True, max_length=10)
    description = serializers.CharField(required=False, allow_blank=True, max_length=255)
    notes = serializers.CharField(required=False, allow_blank=True)
    confirmed = serializers.BooleanField(required=False)
    affects_balance = serializers.BooleanField(required=False)
    raw_payload = serializers.JSONField(required=False)
    raw = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)


class TransactionIntakeBatchSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64)
    source = serializers.CharField(max_length=64, default="open_finance")
    provider_account_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    cursor = serializers.CharField(required=False, allow_blank=True, max_length=255)
    raw_summary = serializers.JSONField(required=False)
    rows = TransactionIntakeRowSerializer(many=True)


class TransactionIntakeSingleRowEnvelopeSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64)
    source = serializers.CharField(max_length=64, default="open_finance")
    provider_account_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    row = TransactionIntakeRowSerializer()


class TransactionIntakeBatchResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionIntakeBatch
        fields = [
            "id",
            "provider",
            "source",
            "provider_account_id",
            "cursor",
            "request_id",
            "idempotency_key",
            "status",
            "row_count",
            "last_error",
            "received_at",
            "applied_at",
        ]
