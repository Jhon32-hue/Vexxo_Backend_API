from django.contrib import admin

from payments.scheduled_payments.models import PaymentScheduleRun, PaymentTemplate


@admin.register(PaymentTemplate)
class PaymentTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "name", "payment_type", "cadence", "is_active", "next_run_at", "budget_scope")
    list_filter = ("payment_type", "cadence", "is_active")
    search_fields = ("name", "beneficiary_name", "external_reference", "owner__username", "owner__email")


@admin.register(PaymentScheduleRun)
class PaymentScheduleRunAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "template", "due_on", "status", "payment_intent", "materialized_transaction", "reminder_stage")
    list_filter = ("status",)
    search_fields = ("idempotency_key", "template__name", "owner__username", "owner__email")
