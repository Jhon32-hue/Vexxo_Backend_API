from __future__ import annotations

from rest_framework import serializers

from finance.accounts.models import Account
from finance.categories.models import Category
from finance.vendors.models import Vendor
from payments.payment_intents.models import (
    PaymentDomainEventOutbox,
    PaymentIntent,
    PaymentOperationalCase,
    PaymentProviderCallbackReceipt,
    PaymentSettlementRecord,
    PayoutBatch,
    PayoutInstruction,
)


def _validate_provider_json_object(*, field_name: str, value, max_keys: int = 128):
    if not isinstance(value, dict):
        raise serializers.ValidationError({field_name: "Debe ser un objeto JSON."})
    if len(value) > max_keys:
        raise serializers.ValidationError({field_name: f"Maximo {max_keys} claves top-level."})
    invalid_keys = [key for key in value.keys() if not isinstance(key, str) or not key.strip()]
    if invalid_keys:
        raise serializers.ValidationError({field_name: "Todas las claves deben ser strings no vacios."})
    return value


class PaymentIntentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = [
            "id",
            "account",
            "category",
            "vendor",
            "payment_type",
            "rail",
            "amount",
            "currency",
            "provider",
            "internal_reference",
            "external_reference",
            "invoice_reference",
            "provider_intent_id",
            "provider_reference",
            "provider_cus",
            "beneficiary_name",
            "beneficiary_document",
            "beneficiary_account_ref",
            "status",
            "source",
            "pricing_snapshot",
            "fee_breakdown",
            "tax_breakdown",
            "provider_metadata",
            "failure_code",
            "failure_message",
            "created_at",
            "dispatched_at",
            "completed_at",
            "updated_at",
        ]
        read_only_fields = fields


class PaymentIntentCreateSerializer(serializers.Serializer):
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all(), required=False, allow_null=True)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)
    vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField(max_length=12, required=False, default="COP")
    provider = serializers.CharField(max_length=64)
    payment_type = serializers.ChoiceField(choices=PaymentIntent.PaymentType.choices, required=False, default=PaymentIntent.PaymentType.OTHER)
    rail = serializers.ChoiceField(choices=PaymentIntent.Rail.choices, required=False, default=PaymentIntent.Rail.OTHER)
    external_reference = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    beneficiary_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    beneficiary_document = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    beneficiary_account_ref = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    invoice_reference = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")

class PaymentPricingPreviewSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    provider = serializers.CharField(max_length=64)
    rail = serializers.CharField(max_length=24)
    country = serializers.CharField(max_length=4, required=False, default="CO")
    payment_type = serializers.CharField(max_length=24, required=False, default=PaymentIntent.PaymentType.OTHER)


class PaymentProviderCallbackSerializer(serializers.Serializer):
    """
    Superficie provider-only.

    Se mantiene flexible porque cada PSP puede variar el payload, pero exigimos
    que llegue como objeto JSON y no como scalar/lista arbitraria.
    """
    provider = serializers.CharField(max_length=64)
    payload = serializers.JSONField()

    def validate_payload(self, value):
        return _validate_provider_json_object(field_name="payload", value=value)


class PaymentWorkerReportSerializer(serializers.Serializer):
    payment_intent_id = serializers.IntegerField()
    status = serializers.ChoiceField(
        choices=[
            PaymentIntent.Status.DISPATCHED,
            PaymentIntent.Status.PROCESSING,
            PaymentIntent.Status.REQUIRES_ACTION,
            PaymentIntent.Status.SUCCEEDED,
            PaymentIntent.Status.SETTLED,
            PaymentIntent.Status.FAILED,
            PaymentIntent.Status.CANCELLED,
            PaymentIntent.Status.REVERSED,
            PaymentIntent.Status.DISPUTED,
        ]
    )
    provider_intent_id = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    provider_reference = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    provider_cus = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    failure_code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    failure_message = serializers.CharField(required=False, allow_blank=True, default="")
    provider_metadata = serializers.JSONField(required=False)

    def validate_provider_metadata(self, value):
        return _validate_provider_json_object(field_name="provider_metadata", value=value, max_keys=32)


class PayoutInstructionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutInstruction
        fields = [
            "id",
            "beneficiary_name",
            "beneficiary_document",
            "beneficiary_account_ref",
            "amount",
            "currency",
            "external_reference",
            "provider_reference",
            "provider_cus",
            "status",
            "fee_breakdown",
            "tax_breakdown",
            "provider_metadata",
            "failure_code",
            "failure_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PayoutBatchCreateSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64)
    rail = serializers.CharField(max_length=24)
    currency = serializers.CharField(max_length=12, required=False, default="COP")
    instructions = serializers.ListField(child=serializers.DictField(), allow_empty=False)


class PayoutBatchSerializer(serializers.ModelSerializer):
    instructions = PayoutInstructionSerializer(many=True, read_only=True)

    class Meta:
        model = PayoutBatch
        fields = [
            "id",
            "provider",
            "rail",
            "currency",
            "status",
            "total_instructions",
            "total_amount",
            "pricing_snapshot",
            "provider_metadata",
            "created_at",
            "updated_at",
            "instructions",
        ]
        read_only_fields = fields


class PaymentDomainEventOutboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentDomainEventOutbox
        fields = "__all__"


class PaymentProviderCallbackReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentProviderCallbackReceipt
        fields = "__all__"


class PaymentSettlementRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentSettlementRecord
        fields = "__all__"


class PaymentOperationalCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentOperationalCase
        fields = "__all__"
