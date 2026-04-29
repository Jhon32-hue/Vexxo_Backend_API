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
    transaction_information = serializers.JSONField(required=False)
    booking_datetime = serializers.DateTimeField(required=False)
    value_datetime = serializers.DateTimeField(required=False)
    credit_debit_indicator = serializers.ChoiceField(
        choices=["debit", "credit"],
        required=False,
        allow_blank=True,
    )
    merchant_name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    merchant_category_code = serializers.CharField(required=False, allow_blank=True, max_length=16)
    counterparty_name = serializers.CharField(required=False, allow_blank=True, max_length=160)
    counterparty_account_ref = serializers.CharField(required=False, allow_blank=True, max_length=128)
    counterparty_account_reference = serializers.CharField(required=False, allow_blank=True, max_length=128)
    rail = serializers.ChoiceField(
        choices=["manual", "open_banking", "bank_transfer", "card", "wallet", "payment_network", "message", "import", "other"],
        required=False,
        allow_blank=True,
    )
    rail_reference = serializers.CharField(required=False, allow_blank=True, max_length=128)
    authorization_status = serializers.ChoiceField(
        choices=["pending", "authorized", "declined", "canceled", "failed", "reversed"],
        required=False,
        allow_blank=True,
    )
    settlement_status = serializers.ChoiceField(
        choices=["pending", "settled", "partial", "failed", "canceled", "reversed"],
        required=False,
        allow_blank=True,
    )
    authorized_at = serializers.DateTimeField(required=False)
    captured_at = serializers.DateTimeField(required=False)
    settled_at = serializers.DateTimeField(required=False)
    reversed_at = serializers.DateTimeField(required=False)
    balance_after_transaction = serializers.DecimalField(max_digits=16, decimal_places=2, required=False)
    original_amount = serializers.DecimalField(max_digits=16, decimal_places=2, required=False)
    original_currency = serializers.CharField(required=False, allow_blank=True, max_length=3)
    fx_rate = serializers.DecimalField(max_digits=16, decimal_places=8, required=False)
    country_code = serializers.CharField(required=False, allow_blank=True, max_length=2)
    channel = serializers.ChoiceField(
        choices=[
            "manual",
            "card_present",
            "ecommerce",
            "bank_transfer",
            "wallet",
            "sms",
            "email",
            "voice",
            "message_inferred",
            "api",
            "import",
            "other",
        ],
        required=False,
        allow_blank=True,
    )
    confidence_score = serializers.IntegerField(required=False, min_value=0, max_value=100)
    data_origin = serializers.ChoiceField(
        choices=["manual", "open_banking", "payment_network", "wallet", "message", "import", "inferred", "payment_intent"],
        required=False,
        allow_blank=True,
    )
    message_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    sender_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    received_at = serializers.DateTimeField(required=False)
    parsed_text = serializers.CharField(required=False, allow_blank=True)
    parser_version = serializers.CharField(required=False, allow_blank=True, max_length=64)
    needs_user_confirmation = serializers.BooleanField(required=False)
    inference_status = serializers.ChoiceField(
        choices=["inferred", "needs_confirmation", "user_confirmed", "provider_confirmed", "rejected"],
        required=False,
        allow_blank=True,
    )
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


class TransactionMessageIntakeEnvelopeSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64, required=False, default="message_parser")
    source = serializers.ChoiceField(choices=["sms", "email", "message"], required=False, default="sms")
    provider_account_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    account_id = serializers.IntegerField(required=False)
    internal_account_id = serializers.IntegerField(required=False)
    message_id = serializers.CharField(max_length=128)
    sender_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    received_at = serializers.DateTimeField()
    text = serializers.CharField()
    currency = serializers.CharField(required=False, allow_blank=True, max_length=3)
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, required=False)
    date = serializers.DateField(required=False)
    type = serializers.ChoiceField(choices=["expense", "income", "transfer"], required=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=255)
    raw_payload = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        if not attrs.get("provider_account_id") and not attrs.get("account_id") and not attrs.get("internal_account_id"):
            raise serializers.ValidationError(
                "Debes enviar provider_account_id o una referencia interna de cuenta (account_id/internal_account_id)."
            )
        return attrs


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
