from django.urls import path, include

urlpatterns = [
    path("mobile/", include("api.mobile.urls")),
    path("runtime/", include("observability.urls")),
    path("internal/accounts/", include("finance.accounts.internal_urls")),
    path("internal/transactions/", include("finance.transactions.internal_urls")),
    path("internal/payments/", include("payments.payment_intents.internal_urls")),
    path("internal/alerts/", include("alerts.alerts.internal_urls")),

    # -------------------
    # IDENTITY
    # -------------------
    path("identity/users/", include("identity.users.urls")),
    path("identity/devices/", include("identity.devices.urls")),
    path("identity/sessions/", include("identity.sessions.urls")),
    path("identity/consents/", include("identity.consents.urls")),
    path("identity/permissions/", include("identity.permissions.urls")),
    path("identity/eventing/", include("identity.eventing.urls")),

    # -------------------
    # FINANCE CORE
    # -------------------
    path("finance/accounts/", include("finance.accounts.urls")),
    path("finance/transactions/", include("finance.transactions.urls")),
    path("finance/categories/", include("finance.categories.urls")),
    path("finance/budgets/", include("finance.budgets.urls")),
    path("finance/debts/", include("finance.debts.urls")),
    path("finance/fx/", include("finance.fx.urls")),
    path("finance/vendors/", include("finance.vendors.urls")),
    path("integrations/open-banking/", include("integrations.open_banking.urls")),
    path("contacts/", include("contacts.urls")),

    # -------------------
    # PLANNING
    # -------------------
    path("planning/goals/", include("planning.goals.urls")),
    path("planning/shared-goals/", include("planning.shared_goals.urls")),

    # -------------------
    # SOCIAL
    # -------------------
    path("social/teams/", include("social.teams.urls")),
    path("social/invitations/", include("social.invitations.urls")),
    path("social/shared-expenses/", include("social.shared_expenses.urls")),

    # -------------------
    # PAYMENTS
    # -------------------
    path("payments/intents/", include("payments.payment_intents.urls")),
    path("payments/scheduled/", include("payments.scheduled_payments.urls")),

    # -------------------
    # DOCUMENTS
    # -------------------
    path("documents/", include("documents.files.urls")),
    path("documents/", include("documents.links_to_transactions.urls")),

    # -------------------
    # ALERTS
    # -------------------
    path("alerts/", include("alerts.alerts.urls")),
    path("alerts/rules/", include("alerts.rules.urls")),

    # -------------------
    # NOTIFICATIONS / REALTIME
    # -------------------
    path("notifications/deliveries/", include("notifications.deliveries.urls")),
    path("notifications/preferences/", include("notifications.preferences.urls")),
    path("realtime/consumers/", include("realtime.consumers.urls")),

    # -------------------
    # REPORTS
    # -------------------
    path("reports/", include("reports.reports.urls")),
    path("reports/", include("reports.monthly_reports.urls")),

    # -------------------
    # SUPPORT / AUDIT
    # -------------------
    path("support/audit/", include("support.audit.urls")),
    path("internal/support/", include("admin_tools.user_lookup.urls")),
    path("internal/support/", include("admin_tools.dashboards.urls")),
    path("internal/support/", include("integrations.open_banking.support_urls")),

]
