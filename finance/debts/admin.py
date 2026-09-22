from django.contrib import admin

from finance.debts.models import Debt, DebtDomainEventOutbox, DebtInstallment, DebtRestructuring


@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "status", "currency", "principal", "start_date")
    list_filter = ("status", "priority", "currency", "frequency")
    search_fields = ("name", "owner__email", "vendor__name")
    readonly_fields = ("status", "closed_at", "created_at", "updated_at")


@admin.register(DebtInstallment)
class DebtInstallmentAdmin(admin.ModelAdmin):
    list_display = ("id", "debt", "number", "due_date", "amount_due", "paid_amount", "status")
    list_filter = ("status", "due_date")
    search_fields = ("debt__name", "owner__email")
    readonly_fields = ("paid_amount", "paid_date", "status", "paid_transaction", "created_at", "updated_at")


@admin.register(DebtRestructuring)
class DebtRestructuringAdmin(admin.ModelAdmin):
    list_display = ("id", "debt", "owner", "effective_date", "created_at")
    search_fields = ("debt__name", "owner__email", "idempotency_key", "reason")
    readonly_fields = [field.name for field in DebtRestructuring._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(DebtDomainEventOutbox)
class DebtDomainEventOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "aggregate_type", "aggregate_id", "status", "occurred_at")
    list_filter = ("status", "event_type")
    search_fields = ("aggregate_id", "idempotency_key", "correlation_id")
    readonly_fields = [field.name for field in DebtDomainEventOutbox._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
