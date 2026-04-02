from django.contrib import admin

from payments.payment_intents.models import PaymentIntent, PayoutBatch, PayoutInstruction


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
