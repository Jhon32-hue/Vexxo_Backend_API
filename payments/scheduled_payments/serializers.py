from __future__ import annotations

from rest_framework import serializers

from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate


class PaymentTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTemplate
        fields = "__all__"
        read_only_fields = ["owner", "legacy_scheduled_payment", "created_at", "updated_at"]


class PaymentScheduleRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentScheduleRun
        fields = "__all__"
        read_only_fields = ["owner", "payment_intent", "idempotency_key", "created_at", "updated_at"]


class PaymentScheduleRunRequestSerializer(serializers.Serializer):
    scheduled_for = serializers.DateTimeField()
    run_payload = serializers.JSONField(required=False)


class PaymentIntentFromScheduleSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    provider = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    rail = serializers.CharField(max_length=24, required=False, allow_blank=True, default="")


class PaymentTemplateFromIntentSerializer(serializers.Serializer):
    payment_intent_id = serializers.IntegerField()
    cadence = serializers.ChoiceField(choices=PaymentTemplate.Cadence.choices, required=False, default=PaymentTemplate.Cadence.MONTHLY)
    interval_count = serializers.IntegerField(required=False, min_value=1, default=1)
