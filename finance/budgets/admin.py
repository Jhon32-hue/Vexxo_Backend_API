from django.contrib import admin

from finance.budgets.models import (
    AccountBudget,
    Budget,
    SharedBudget,
    SharedBudgetTemplateLink,
    SharedBudgetTransactionLink,
)


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "month", "category", "amount")
    list_filter = ("month", "category")
    search_fields = ("owner__email", "category__name", "month")


@admin.register(AccountBudget)
class AccountBudgetAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "month", "account", "amount")
    list_filter = ("month", "account")
    search_fields = ("owner__email", "account__name", "month")


@admin.register(SharedBudget)
class SharedBudgetAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "owner", "month", "name", "amount")
    list_filter = ("month", "team")
    search_fields = ("team__name", "owner__email", "name", "month")


@admin.register(SharedBudgetTransactionLink)
class SharedBudgetTransactionLinkAdmin(admin.ModelAdmin):
    list_display = ("id", "shared_budget", "transaction", "linked_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("shared_budget__name", "transaction__description", "linked_by__email")


@admin.register(SharedBudgetTemplateLink)
class SharedBudgetTemplateLinkAdmin(admin.ModelAdmin):
    list_display = ("id", "shared_budget", "payment_template", "linked_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("shared_budget__name", "payment_template__name", "linked_by__email")
