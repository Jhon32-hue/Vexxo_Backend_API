from __future__ import annotations

from rest_framework import serializers

from finance.accounts.models.account import Account
from finance.accounts.services.permission_service import account_scope_for_user
from finance.transactions.Models import TransactionInferenceRequest


class TransactionInferenceRequestCreateSerializer(serializers.Serializer):
    account_id = serializers.IntegerField()
    audio_object_ref = serializers.CharField(max_length=512)
    audio_content_type = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    audio_duration_ms = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    language = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    provider = serializers.CharField(max_length=64, required=False, allow_blank=True, default="voice_ai")

    def validate(self, attrs):
        forbidden_fields = []
        if "raw_payload" in getattr(self, "initial_data", {}):
            forbidden_fields.append("raw_payload")
        if "normalized_payload" in getattr(self, "initial_data", {}):
            forbidden_fields.append("normalized_payload")
        if forbidden_fields:
            raise serializers.ValidationError(
                {field: "Este campo no puede ser enviado por cliente en el endpoint publico." for field in forbidden_fields}
            )
        return attrs

    def validate_account_id(self, value):
        user = self.context["request"].user
        account = account_scope_for_user(user, Account.objects.all()).filter(pk=value).first()
        if account is None:
            raise serializers.ValidationError("Cuenta no encontrada o sin acceso.")
        return account


class TransactionInferenceRequestSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    requested_by_id = serializers.IntegerField(read_only=True)
    intake_batch_id = serializers.SerializerMethodField(read_only=True)
    receipt_ids = serializers.SerializerMethodField(read_only=True)
    transaction_ids = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TransactionInferenceRequest
        fields = [
            "id",
            "owner",
            "requested_by_id",
            "account",
            "account_name",
            "source",
            "provider",
            "request_id",
            "idempotency_key",
            "status",
            "audio_object_ref",
            "audio_content_type",
            "audio_duration_ms",
            "language",
            "provider_request_id",
            "provider_job_id",
            "provider_correlation_id",
            "transcript",
            "transcript_confidence",
            "parser_version",
            "intake_batch_id",
            "receipt_ids",
            "transaction_ids",
            "result_summary",
            "raw_payload",
            "normalized_payload",
            "retry_count",
            "next_attempt_at",
            "last_error",
            "dispatch_backend",
            "last_dispatch_result",
            "dispatch_attempt_count",
            "last_dispatch_attempt_at",
            "last_dispatch_error",
            "local_worker_locked_at",
            "local_worker_locked_by",
            "stale_recovery_count",
            "last_recovered_at",
            "last_operational_issue",
            "requested_at",
            "processing_started_at",
            "applied_at",
            "failed_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_intake_batch_id(self, obj):
        return str(obj.intake_batch_id or "")

    def get_receipt_ids(self, obj):
        if not obj.intake_batch_id:
            return []
        return [str(receipt.pk) for receipt in obj.intake_batch.receipts.all()]

    def get_transaction_ids(self, obj):
        if not obj.intake_batch_id:
            return []
        return [
            str(receipt.materialized_transaction_id)
            for receipt in obj.intake_batch.receipts.all()
            if receipt.materialized_transaction_id
        ]
