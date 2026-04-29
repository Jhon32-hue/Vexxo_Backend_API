from django.contrib import admin

from finance.transactions.Models import TransactionInferenceRequest


@admin.register(TransactionInferenceRequest)
class TransactionInferenceRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "provider", "status", "account", "requested_by", "requested_at", "retry_count")
    list_filter = ("source", "provider", "status")
    search_fields = ("id", "request_id", "idempotency_key", "audio_object_ref", "provider_request_id", "provider_job_id")
    readonly_fields = ("id", "requested_at", "updated_at", "applied_at", "failed_at")
