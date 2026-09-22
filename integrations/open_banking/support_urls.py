from django.urls import path

from integrations.open_banking.support_views import OpenBankingSupportTimelineView


urlpatterns = [
    path(
        "open-banking/connections/<uuid:public_id>/timeline/",
        OpenBankingSupportTimelineView.as_view(),
        name="support-open-banking-timeline",
    ),
]
