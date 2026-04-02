from django.contrib import admin

from payments.payment_intents.models import (
    PaymentDomainEventOutbox,
    PaymentIntent,
    PaymentOperationalCase,
    PaymentProviderCallbackReceipt,
    PaymentSettlementRecord,
    PayoutBatch,
    PayoutInstruction,
)


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "payment_type", "rail", "amount", "currency", "provider", "status", "created_at")
    list_filter = ("status", "provider", "currency", "payment_type", "rail")
    search_fields = (
        "external_reference",
        "internal_reference",
        "invoice_reference",
        "provider_intent_id",
        "provider_reference",
        "provider_cus",
        "idempotency_key",
        "beneficiary_name",
        "owner__username",
        "owner__email",
    )


@admin.register(PayoutBatch)
class PayoutBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "provider", "rail", "currency", "status", "total_instructions", "total_amount", "created_at")
    list_filter = ("status", "provider", "rail", "currency")
    search_fields = ("idempotency_key", "owner__username", "owner__email")


@admin.register(PayoutInstruction)
class PayoutInstructionAdmin(admin.ModelAdmin):
    list_display = ("id", "batch", "beneficiary_name", "amount", "currency", "status", "provider_reference")
    list_filter = ("status", "currency")
    search_fields = ("beneficiary_name", "beneficiary_account_ref", "provider_reference", "provider_cus", "external_reference")


@admin.register(PaymentDomainEventOutbox)
class PaymentDomainEventOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "aggregate_type", "aggregate_id", "event_type", "status", "retry_count", "occurred_at", "published_at")
    list_filter = ("status", "event_type")
    search_fields = ("aggregate_id", "idempotency_key", "correlation_id", "request_id")


@admin.register(PaymentProviderCallbackReceipt)
class PaymentProviderCallbackReceiptAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "callback_type", "status", "signature_valid", "payment_intent", "created_at")
    list_filter = ("provider", "callback_type", "status", "signature_valid")
    search_fields = ("provider_reference", "provider_intent_id", "external_reference", "idempotency_key")


@admin.register(PaymentSettlementRecord)
class PaymentSettlementRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "payment_intent", "provider", "rail", "amount", "status", "settled_at", "recorded_at")
    list_filter = ("provider", "rail", "status")
    search_fields = ("settlement_reference", "provider_reference", "provider_cus")


@admin.register(PaymentOperationalCase)
class PaymentOperationalCaseAdmin(admin.ModelAdmin):
    list_display = ("id", "payment_intent", "provider", "kind", "status", "amount", "currency", "opened_at")
    list_filter = ("provider", "kind", "status", "currency")
    search_fields = ("provider_reference", "provider_case_reference")
