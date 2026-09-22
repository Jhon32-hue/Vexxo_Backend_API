from __future__ import annotations

from rest_framework import serializers

from finance.budgets.models import SharedBudget
from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate


PUBLIC_RESERVED_JSON_KEYS = {
    "owner_id",
    "template_id",
    "payment_intent_id",
    "materialized_transaction_id",
    "legacy_source",
    "legacy_scheduled_payment_id",
    "retry_of_schedule_run_id",
    "retried_by_schedule_run_id",
    "status",
}


def _validate_public_json_object(*, field_name: str, value, max_keys: int = 16):
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError({field_name: "Debe ser un objeto JSON."})
    invalid_keys = [key for key in value.keys() if not isinstance(key, str) or not key.strip()]
    if invalid_keys:
        raise serializers.ValidationError({field_name: "Todas las claves deben ser strings no vacios."})
    if len(value) > max_keys:
        raise serializers.ValidationError({field_name: f"Maximo {max_keys} claves top-level."})
    reserved = sorted(PUBLIC_RESERVED_JSON_KEYS.intersection(value.keys()))
    if reserved:
        raise serializers.ValidationError(
            {field_name: f"Contiene claves reservadas no permitidas: {', '.join(reserved)}."}
        )
    return value


class PaymentTemplateSerializer(serializers.ModelSerializer):
    """
    Superficie publica estricta.

    Este serializer puede aceptar algunos metadatos JSON (`execution_defaults`)
    pero no debe permitir claves de control internas del scheduler ni del legacy.
    """
    budget_context_shared_budget = serializers.PrimaryKeyRelatedField(
        queryset=SharedBudget.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = PaymentTemplate
        fields = "__all__"
        read_only_fields = ["owner", "idempotency_key", "created_at", "updated_at", "budget_attribution_source"]

    def validate_execution_defaults(self, value):
        return _validate_public_json_object(field_name="execution_defaults", value=value, max_keys=8)


class PaymentScheduleRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentScheduleRun
        fields = "__all__"
        read_only_fields = ["owner", "payment_intent", "idempotency_key", "created_at", "updated_at"]


class PaymentScheduleRunRequestSerializer(serializers.Serializer):
    """
    Superficie publica estricta.

    `run_payload` es metadata de cliente/control de UX, no un canal para inyectar
    campos internos de lifecycle.
    """
    scheduled_for = serializers.DateTimeField()
    run_payload = serializers.JSONField(required=False)

    def validate_run_payload(self, value):
        return _validate_public_json_object(field_name="run_payload", value=value, max_keys=8)


class PaymentScheduleRunResolveSerializer(serializers.Serializer):
    paid_on = serializers.DateField(required=False)
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentScheduleRunPostponeSerializer(serializers.Serializer):
    new_due_on = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentScheduleRunSkipSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentScheduleRunCancelSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentScheduleRunRetrySerializer(serializers.Serializer):
    new_due_on = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentIntentFromScheduleSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    provider = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    rail = serializers.CharField(max_length=24, required=False, allow_blank=True, default="")


class PaymentTemplateFromIntentSerializer(serializers.Serializer):
    payment_intent_id = serializers.IntegerField()
    cadence = serializers.ChoiceField(choices=PaymentTemplate.Cadence.choices, required=False, default=PaymentTemplate.Cadence.MONTHLY)
    interval_count = serializers.IntegerField(required=False, min_value=1, default=1)
