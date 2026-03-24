from django.urls import path, include

urlpatterns = [

    # -------------------
    # IDENTITY
    # -------------------
    path("identity/users/", include("identity.users.urls")),

    # -------------------
    # FINANCE CORE
    # -------------------
    path("finance/accounts/", include("finance.accounts.urls")),
    path("finance/transactions/", include("finance.transactions.urls")),
    path("finance/categories/", include("finance.categories.urls")),
    path("finance/debts/", include("finance.debts.urls")),
    path("finance/fx/", include("finance.fx.urls")),
    path("finance/vendors/", include("finance.vendors.urls")),

    # -------------------
    # PLANNING
    # -------------------
    path("planning/goals/", include("planning.goals.urls")),

    # -------------------
    # SOCIAL
    # -------------------
    path("social/teams/", include("social.teams.urls")),

    # -------------------
    # PAYMENTS
    # -------------------

    # -------------------
    # DOCUMENTS
    # -------------------

    # -------------------
    # ALERTS
    # -------------------
    path("alerts/", include("alerts.alerts.urls")),
    path("alerts/rules/", include("alerts.rules.urls")),

    # -------------------
    # NOTIFICATIONS / REALTIME
    # -------------------
    path("notifications/deliveries/", include("notifications.deliveries.urls")),
    path("realtime/consumers/", include("realtime.consumers.urls")),

    # -------------------
    # REPORTS
    # -------------------
    path("reports/", include("reports.reports.urls")),

    # -------------------
    # SUPPORT / AUDIT
    # -------------------
    path("support/audit/", include("support.audit.urls")),

]
