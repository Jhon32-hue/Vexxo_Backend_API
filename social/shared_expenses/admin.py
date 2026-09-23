from django.contrib import admin

from social.shared_expenses.models import (
    SharedExpense,
    SharedExpenseDomainEventOutbox,
    SharedExpenseSettlement,
    SharedExpenseShare,
)

admin.site.register(SharedExpense)
admin.site.register(SharedExpenseShare)
admin.site.register(SharedExpenseSettlement)
admin.site.register(SharedExpenseDomainEventOutbox)
